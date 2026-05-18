#!/usr/bin/env python3
"""Boot a shell from the substrate's DB.

Usage:  python -m shell_core.scripts.run [shortname]
        (or via Makefile: `make launch` for picker,
        `make launch-<shortname>` to skip picker)

With no arg: lists shells, prompts for selection.
With a shortname: looks up that shell directly; errors if not found.
Either way: renders a per-shell CLAUDE.md from live DB state, opens a new
archive row, then exec's claude in the shell's workspace dir.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import os
import secrets
import sqlite3
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from db_init import ensure_forge
from shared_dirs import SHARED_ROOT, ensure_shared_dirs, shared_dir_container_path

SUBSTRATE_ROOT = Path(__file__).resolve().parents[2]
DB_PATH        = SUBSTRATE_ROOT / "shell_core" / "shell_db.db"
TEMPLATE_PATH  = SUBSTRATE_ROOT / "shell_core" / "templates" / "boot.md"
SHELLS_DIR     = SUBSTRATE_ROOT / "shells"

BACKUP_DIR     = Path.home() / "db_backups" / "dos-arch"
BOOT_SNAPSHOT_PREFIX = "shell_db.boot."          # distinguishes from `make db-backup` (`shell_db.bak.*`)
BOOT_SNAPSHOT_KEEP   = 5                         # rolling retention; older snapshots pruned

DIR_SENTINEL = ".shell_managed"   # marker file the script writes; cleanup only rms dirs that have it

# ── Docker (Phase 3 — shells run in per-shell containers) ─────────────────────
CONTAINER_PREFIX = "shell-"            # container name = shell-<shortname>
SHELL_IMAGE      = "dos-shell:latest"
DOCKER_NETWORK   = "dos-net"

# Broker's /anthropic route — API shells (shells.api_auth=1) are pointed here
# instead of api.anthropic.com; the broker holds and injects the real key.
BROKER_ANTHROPIC_URL = "http://dos-broker:8788/anthropic"


# ── DB helpers ────────────────────────────────────────────────────────────────

def open_db() -> sqlite3.Connection:
    # Tripwire: refuse to proceed if the DB is missing or 0-byte. sqlite3.connect()
    # silently creates an empty file when the path doesn't exist, which masks
    # data-loss incidents (DB removed by a stray git op, accidental rm, etc.).
    if not DB_PATH.exists():
        sys.exit(
            f"FATAL: DB not found at {DB_PATH}\n"
            f"  Restore the latest snapshot from {BACKUP_DIR}, or\n"
            f"  run `make bootstrap` if this is a fresh substrate."
        )
    if DB_PATH.stat().st_size == 0:
        sys.exit(
            f"FATAL: DB at {DB_PATH} is 0 bytes — likely lost via a git op or\n"
            f"  re-created empty by a stray sqlite3.connect(). Do not boot.\n"
            f"  Restore the latest snapshot from {BACKUP_DIR}."
        )
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        con.execute("SELECT 1 FROM shells LIMIT 1")  # smoke
        return con
    except sqlite3.Error as e:
        sys.exit(f"FATAL: cannot access DB at {DB_PATH}: {e}")


def snapshot_db() -> None:
    """Boot-time snapshot of shell_db.db with rolling retention.

    Writes shell_db.boot.<TS>.db into ~/db_backups/dos-arch/ and prunes
    oldest snapshots beyond BOOT_SNAPSHOT_KEEP. Manual `make db-backup`
    snapshots use a different prefix and are not touched.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"{BOOT_SNAPSHOT_PREFIX}{ts}.db"
    shutil.copy2(DB_PATH, target)

    snapshots = sorted(
        BACKUP_DIR.glob(f"{BOOT_SNAPSHOT_PREFIX}*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in snapshots[BOOT_SNAPSHOT_KEEP:]:
        old.unlink()


def list_shells(con: sqlite3.Connection, user_id: int | None = None) -> list[sqlite3.Row]:
    """All shells (user_id=None) or a user's own + all shared shells."""
    if user_id is None:
        return con.execute("""
            SELECT shell_id, display_name, shortname, mandate, is_shared, is_admin
            FROM shells
            ORDER BY shell_id
        """).fetchall()
    return con.execute("""
        SELECT shell_id, display_name, shortname, mandate, is_shared, is_admin
        FROM shells
        WHERE user_id=? OR is_shared=1
        ORDER BY is_shared, shell_id
    """, (user_id,)).fetchall()


def count_owned_shells(con: sqlite3.Connection, user_id: int) -> int:
    return con.execute(
        "SELECT COUNT(*) FROM shells WHERE user_id=? AND is_shared=0",
        (user_id,),
    ).fetchone()[0]


def get_shared_shell(con: sqlite3.Connection) -> sqlite3.Row:
    """Return the canonical shared bootstrap shell (Forge). Errors if missing."""
    row = con.execute("""
        SELECT shell_id, display_name, shortname, mandate, is_shared, is_admin
        FROM shells WHERE is_shared=1
        ORDER BY shell_id LIMIT 1
    """).fetchone()
    if row is None:
        sys.exit("FATAL: no shared shell in DB. Cannot bootstrap a new user.")
    return row


# ── Auth ──────────────────────────────────────────────────────────────────────

SCRYPT_N    = 16384
SCRYPT_R    = 8
SCRYPT_P    = 1
SCRYPT_DKLEN = 32


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN,
    )


def lookup_user(con: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return con.execute(
        "SELECT user_id, username, password_hash, password_salt "
        "FROM users WHERE LOWER(username)=LOWER(?) AND is_active=1",
        (username,),
    ).fetchone()


def verify_password(row: sqlite3.Row, password: str) -> bool:
    """Constant-ish-time check. Always run scrypt even on missing-hash rows."""
    if not row or not row["password_hash"] or not row["password_salt"]:
        _hash(password, b"\x00" * 16)
        return False
    salt   = base64.b64decode(row["password_salt"])
    stored = base64.b64decode(row["password_hash"])
    return hmac.compare_digest(stored, _hash(password, salt))


def authenticate(con: sqlite3.Connection) -> tuple[sqlite3.Row, bool]:
    """Username-first auth. Returns (user_row, password_verified).

    A user with zero owned shells gets in on username alone and is sent to
    the shared bootstrap shell. Anyone with ≥1 owned shell must enter the
    correct password.
    """
    username = input("Username: ").strip()
    if not username:
        sys.exit("aborted")

    row = lookup_user(con, username)
    if row is None:
        # Run a dummy hash so missing-user timing matches wrong-password timing.
        _hash("dummy", b"\x00" * 16)
        sys.exit("auth failed")

    if count_owned_shells(con, row["user_id"]) == 0:
        return row, False

    password = getpass.getpass("Password: ")
    if not verify_password(row, password):
        sys.exit("auth failed")
    return row, True


# ── UI ────────────────────────────────────────────────────────────────────────

def print_picker(shells: list[sqlite3.Row]) -> None:
    if not shells:
        sys.exit("FATAL: no shells in DB. Cannot boot.")
    name_w = max(len(s["display_name"] or "") for s in shells) + 2
    short_w = max(len(s["shortname"] or "") for s in shells) + 2
    print(f"\n{'ID':>3}  {'Name':<{name_w}}{'Shortname':<{short_w}}Mandate")
    print(f"{'─'*3}  {'─'*(name_w-2):<{name_w}}{'─'*(short_w-2):<{short_w}}{'─'*40}")
    for s in shells:
        print(f"{s['shell_id']:>3}  {(s['display_name'] or ''):<{name_w}}{(s['shortname'] or ''):<{short_w}}{(s['mandate'] or '')}")
    print()


def prompt_pick(shells: list[sqlite3.Row]) -> sqlite3.Row:
    valid_ids = {s["shell_id"] for s in shells}
    while True:
        choice = input("Pick (ID): ").strip()
        if not choice:
            continue
        try:
            n = int(choice)
        except ValueError:
            print(f"  not a number")
            continue
        if n not in valid_ids:
            print(f"  no shell with id={n}")
            continue
        return next(s for s in shells if s["shell_id"] == n)


# ── Workspace dir management ──────────────────────────────────────────────────

def sync_shell_dirs(shells: list[sqlite3.Row]) -> None:
    """Create dirs for shells that lack one; remove dirs whose shell no longer exists."""
    SHELLS_DIR.mkdir(exist_ok=True)
    active_shortnames = {s["shortname"] for s in shells if s["shortname"]}

    # Create
    for shortname in active_shortnames:
        d = SHELLS_DIR / shortname
        if not d.exists():
            d.mkdir(parents=True)
            (d / DIR_SENTINEL).write_text("managed by shell_core/scripts/run.py\n")

    # Cleanup
    for entry in SHELLS_DIR.iterdir():
        if not entry.is_dir():
            continue
        if entry.name in active_shortnames:
            continue
        # Only remove if we managed it (has sentinel)
        if (entry / DIR_SENTINEL).exists():
            shutil.rmtree(entry)
            print(f"cleaned up orphaned shell dir: {entry.name}")
        else:
            print(f"warning: dir {entry} has no shell match and no sentinel — leaving alone", file=sys.stderr)


# ── Container lifecycle ───────────────────────────────────────────────────────

def _docker(*args: str) -> subprocess.CompletedProcess:
    """Run a docker CLI command, capturing output. Exits cleanly if docker
    is not on PATH (e.g. launcher not running as the dos-arch service user)."""
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True)
    except FileNotFoundError:
        sys.exit("FATAL: `docker` not found on PATH — the launcher must run as "
                 "the dos-arch user, with rootless Docker set up.")


def ensure_container(shortname: str, workdir: Path, is_admin: bool = False) -> str:
    """Ensure the shell's persistent container exists and is running.

    run-if-missing / start-if-stopped / no-op-if-running. The container is
    persistent: the dos-shell image's CMD (`sleep infinity` under tini)
    holds it open; a session attaches via `docker exec`. The shell's workdir
    is bind-mounted to /workspace so the rendered CLAUDE.md is visible
    inside. Anthropic auth is intentionally NOT injected at the container
    level — it is set per shell type on the `docker exec` (see main()):
    CLI shells browser-auth, API shells route through the broker.

    Returns the container name. Exits on docker failure; the caller runs
    this BEFORE opening a session so a failure burns no session number.
    """
    name = f"{CONTAINER_PREFIX}{shortname}"
    state = _docker("inspect", "-f", "{{.State.Running}}", name)

    if state.returncode != 0:                       # container does not exist
        # Host↔container shared folder. Mounted at /root/shared so the
        # container's `~/shared` (HOME=/root) resolves to it — the path the
        # system prompt's `shared` definition names. (Sys-Admin E2E gap 13.)
        # SHARED_ROOT is passwd-anchored — see shared_dirs.py.
        shared_dir = SHARED_ROOT
        shared_dir.mkdir(exist_ok=True)
        run_args = [
            "run", "-d",
            "--name", name,
            "--network", DOCKER_NETWORK,
            "-v", f"{workdir}:/workspace",
            "-v", f"{shared_dir}:/root/shared",
        ]
        if is_admin:
            # Admin shells (Sys-Admin) get the substrate repo mounted RW, so
            # they can author migrations and edit substrate source in place.
            # The privileged *execution* (recompose) still happens host-side.
            run_args += ["-v", f"{SUBSTRATE_ROOT}:/substrate"]
        run_args += ["--restart", "unless-stopped", SHELL_IMAGE]
        created = _docker(*run_args)
        if created.returncode != 0:
            sys.exit(f"FATAL: could not create container {name}:\n"
                     f"  {created.stderr.strip()}")
        print(f"→ created container {name}"
              + ("  ·  +/substrate (admin)" if is_admin else ""))
    elif state.stdout.strip() != "true":            # exists but stopped
        started = _docker("start", name)
        if started.returncode != 0:
            sys.exit(f"FATAL: could not start container {name}:\n"
                     f"  {started.stderr.strip()}")
        print(f"→ started container {name}")

    return name


# ── State render ──────────────────────────────────────────────────────────────

def render_seed(con: sqlite3.Connection, shell_id: int) -> str:
    rows = con.execute("""
        SELECT entry_date, body FROM shell_identity_entries
        WHERE shell_id=? AND kind='seed' AND is_deleted=0 AND retired_at IS NULL
        ORDER BY entry_date, entry_id
    """, (shell_id,)).fetchall()
    if not rows:
        return "(none)"
    out = []
    for r in rows:
        out.append(f"### {r['entry_date']}\n{r['body']}")
    return "\n\n".join(out)


def render_lns(con: sqlite3.Connection, shell_id: int) -> str:
    rows = con.execute("""
        SELECT body FROM shell_identity_entries
        WHERE shell_id=? AND kind='lns' AND is_deleted=0 AND retired_at IS NULL
        ORDER BY entry_date, entry_id
    """, (shell_id,)).fetchall()
    if not rows:
        return "(none)"
    return "\n\n".join(r["body"] for r in rows)


def render_projects(con: sqlite3.Connection, shell_id: int) -> str:
    rows = con.execute("""
        SELECT p.shortname, p.purpose, ps.role
        FROM projects p
        JOIN project_shells ps ON ps.project_id = p.project_id
        WHERE ps.shell_id=? AND ps.is_deleted=0
          AND COALESCE(p.is_deleted,0)=0
          AND (p.status IS NULL OR p.status NOT IN ('archived','dropped'))
        ORDER BY p.shortname
    """, (shell_id,)).fetchall()
    if not rows:
        return "(none)"
    lines = []
    for r in rows:
        role_part = f" ({r['role']})" if r["role"] else ""
        purpose = r["purpose"] or "(no purpose set)"
        lines.append(f"- {r['shortname']}{role_part}: {purpose}")
    return "\n".join(lines)


def render_operator(user_row: sqlite3.Row) -> str:
    """Identifies who is driving this session. Crucial for shared shells
    (Forge needs to know which user to assign newly-bootstrapped shells to)
    and informational on owned shells."""
    return (
        "| | |\n"
        "|---|---|\n"
        f"| **user_id** | `{user_row['user_id']}` |\n"
        f"| **username** | {user_row['username']} |"
    )


def render_identity(shell_row: sqlite3.Row) -> str:
    """Markdown table of the shell's identity columns. Empty cells render as '—'."""
    def cell(v):
        s = (v or "").strip() if isinstance(v, str) else (v or "")
        return s if s else "—"
    return (
        "| | |\n"
        "|---|---|\n"
        f"| **Name** | {cell(shell_row['display_name'])} |\n"
        f"| **Shortname** | {cell(shell_row['shortname'])} |\n"
        f"| **Partner** | {cell(shell_row['partner'])} |\n"
        f"| **Role** | {cell(shell_row['role'])} |\n"
        f"| **Mandate** | {cell(shell_row['mandate'])} |"
    )


def render_shared_dirs(shell_row: sqlite3.Row) -> str:
    """The shell's own scratch space under the shared mount — rendered as the
    container-relative path the shell sees from inside its own container."""
    base = shared_dir_container_path(shell_row["shell_id"], shell_row["shortname"])
    return (
        f"`{base}/` is your directory inside the shared mount — it contains\n"
        "`redlines/`, `review/`, `repos/`, and `backups/`. This dir and its\n"
        "subdirs are yours, to use in collaboration with FnB. Other shells can\n"
        "see it; by convention it is yours."
    )


def render_skills(con: sqlite3.Connection, shell_id: int) -> str:
    rows = con.execute("""
        SELECT s.name, s.description
        FROM skills s
        JOIN shell_skills ss ON ss.skill_id = s.skill_id
        WHERE ss.shell_id=? AND s.is_deleted=0
        ORDER BY s.name
    """, (shell_id,)).fetchall()
    if not rows:
        return "(none)"
    lines = []
    for r in rows:
        desc = (r["description"] or "").strip().split("\n")[0]
        lines.append(f"- **{r['name']}** — {desc}")
    return "\n".join(lines)


def fetch_counts(con: sqlite3.Connection, shell_id: int) -> dict:
    seed_count = con.execute(
        "SELECT COUNT(*) FROM shell_identity_entries WHERE shell_id=? AND kind='seed' AND is_deleted=0 AND retired_at IS NULL",
        (shell_id,),
    ).fetchone()[0]
    lns_count = con.execute(
        "SELECT COUNT(*) FROM shell_identity_entries WHERE shell_id=? AND kind='lns' AND is_deleted=0 AND retired_at IS NULL",
        (shell_id,),
    ).fetchone()[0]
    flag_count = con.execute(
        "SELECT COUNT(*) FROM flags WHERE shell_id=? AND resolved=0 AND is_deleted=0",
        (shell_id,),
    ).fetchone()[0]
    return {"seed": seed_count, "lns": lns_count, "flags": flag_count}


# ── Session archive ───────────────────────────────────────────────────────────

def open_session(con: sqlite3.Connection, shell_id: int) -> tuple[str, int]:
    """Compute next session_id, INSERT archive row, set active_archive_id. Returns (session_id, archive_id)."""
    last = con.execute(
        "SELECT MAX(CAST(session_id AS INTEGER)) FROM shell_memory_archives WHERE shell_id=?",
        (shell_id,),
    ).fetchone()[0]
    next_session = f"{(last or 0) + 1:04d}"
    # UTC, not host-local: shell containers run on UTC, so a shell appending
    # [HH:MM] narrative lines uses UTC. The launcher writes the session-start
    # line; matching UTC keeps every [HH:MM] entry on one clock and linearly
    # sortable. (Sys-Admin E2E gap 12 — launcher/container TZ drift.)
    now_hm = datetime.now(timezone.utc).strftime("%H:%M")
    today = str(date.today())
    narrative = f"# {next_session} | {today} | session opened\n\n## Narrative\n\n[{now_hm}] Session start.\n"
    cur = con.execute("""
        INSERT INTO shell_memory_archives (shell_id, session_id, date, full_narrative)
        VALUES (?, ?, ?, ?)
    """, (shell_id, next_session, today, narrative))
    archive_id = cur.lastrowid
    con.execute("UPDATE shells SET active_archive_id=? WHERE shell_id=?", (archive_id, shell_id))
    con.commit()
    return next_session, archive_id


# ── Compose ───────────────────────────────────────────────────────────────────

def compose_claude_md(
    shell_row: sqlite3.Row,
    user_row: sqlite3.Row,
    session_id: str,
    archive_id: int,
    counts: dict,
    seed: str, lns: str, projects: str, skills: str,
) -> str:
    template = TEMPLATE_PATH.read_text()
    current_state = (shell_row["current_state"] or "(none)").strip()
    additional_prompt = (shell_row["additional_prompt"] or "").strip()
    # <self> sentinel → this shell's id (lets templates be cloned across shells safely)
    additional_prompt = additional_prompt.replace("<self>", str(shell_row["shell_id"]))
    identity = render_identity(shell_row)
    operator = render_operator(user_row)
    shared_dirs = render_shared_dirs(shell_row)

    parts = [
        template.rstrip(),
        "",
        "## ACTIVE SESSION",
        "",
        f"- shell_id: `{shell_row['shell_id']}`",
        f"- display_name: `{shell_row['display_name']}`",
        f"- shortname: `{shell_row['shortname']}`",
        f"- session_id: `{session_id}`",
        f"- archive_id: `{archive_id}`",
        "",
        "---",
        "",
        "## OPERATOR",
        "",
        operator,
        "",
        "---",
        "",
        "## IDENTITY",
        "",
        identity,
        "",
        "---",
        "",
        "## YOUR SPACE",
        "",
        shared_dirs,
        "",
        "---",
        "",
        "## SYSTEM PROMPT",
        "",
        additional_prompt,
        "",
        "---",
        "",
        "## CURRENT STATE",
        "",
        current_state,
        "",
        "---",
        "",
        "## SEED",
        "",
        seed,
        "",
        "---",
        "",
        "## LESSONS & STANCES",
        "",
        lns,
        "",
        "---",
        "",
        "## ACTIVE PROJECTS",
        "",
        projects,
        "",
        "---",
        "",
        "## SKILLS",
        "",
        skills,
        "",
        "---",
        "",
        "## STATUS",
        "",
        f"- **Session:** {session_id}",
        f"- **Seed:** {counts['seed']}",
        f"- **L&S:** {counts['lns']}",
        f"- **Flags:** {counts['flags']} open → `surface_flags`",
        "",
    ]
    return "\n".join(parts)


def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    con = open_db()
    snapshot_db()

    try:
        forge_id, created = ensure_forge(con)
    except FileNotFoundError as e:
        sys.exit(f"FATAL: cannot seed Forge — {e}")
    if created:
        con.commit()
        print(f"→ seeded Forge at shell_id={forge_id} (was missing from DB)")

    sync_shell_dirs(list_shells(con))

    requested = sys.argv[1].strip() if len(sys.argv) > 1 else None

    user, password_verified = authenticate(con)

    if not password_verified:
        # User has no owned shells: drop straight into the shared bootstrap shell.
        chosen = get_shared_shell(con)
        if requested and requested != chosen["shortname"]:
            sys.exit(
                f"{user['username']} has no owned shells yet — must bootstrap via "
                f"'{chosen['shortname']}' before launching anything else."
            )
    else:
        user_shells = list_shells(con, user_id=user["user_id"])
        if requested:
            chosen = next((s for s in user_shells if s["shortname"] == requested), None)
            if chosen is None:
                valid = ", ".join(s["shortname"] for s in user_shells if s["shortname"]) or "(none)"
                sys.exit(f"no shell '{requested}' available to {user['username']}. Available: {valid}")
        else:
            print_picker(user_shells)
            chosen = prompt_pick(user_shells)

    seed     = render_seed(con, chosen["shell_id"])
    lns      = render_lns(con, chosen["shell_id"])
    projects = render_projects(con, chosen["shell_id"])
    skills   = render_skills(con, chosen["shell_id"])
    counts   = fetch_counts(con, chosen["shell_id"])

    workdir = SHELLS_DIR / chosen["shortname"]
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / DIR_SENTINEL).write_text("managed by shell_core/scripts/run.py\n")

    # Verify-and-create the shell's scratch tree under ~/shared. Idempotent —
    # catches shells created via POST /shells, whose creation runs inside the
    # dos-api container and so cannot reach the host's ~/shared.
    ensure_shared_dirs(chosen["shell_id"], chosen["shortname"])

    # Ensure the shell's container is up BEFORE opening a session — a failed
    # container launch must not burn a session number.
    container = ensure_container(chosen["shortname"], workdir, is_admin=bool(chosen["is_admin"]))

    session_id, archive_id = open_session(con, chosen["shell_id"])

    # Rotate the shell's substrate-API token every render. Low-sensitivity —
    # it reaches only this shell's own memory — and short-lived: the DB keeps
    # just the SHA-256, so the prior token dies the moment this one is stored.
    api_token = secrets.token_urlsafe(32)
    con.execute(
        "UPDATE shells SET api_key_hash=? WHERE shell_id=?",
        (hashlib.sha256(api_token.encode()).hexdigest(), chosen["shell_id"]),
    )
    con.commit()

    # Re-fetch after opening session so the row has updated active_archive_id
    full = con.execute(
        "SELECT shell_id, display_name, shortname, partner, role, mandate, current_state, additional_prompt, api_auth FROM shells WHERE shell_id=?",
        (chosen["shell_id"],),
    ).fetchone()

    content = compose_claude_md(full, user, session_id, archive_id, counts, seed, lns, projects, skills)
    atomic_write(workdir / "CLAUDE.md", content)

    con.close()

    print(f"\n→ booted {chosen['display_name']} (shell_id={chosen['shell_id']}, session={session_id})")
    print(f"→ container: {container}  ·  {workdir} → /workspace")
    print(f"→ docker exec claude\n")

    # Hand the rotated API token to the container by env-passthrough: `-e
    # DOS_API_TOKEN` with no value makes docker read it from this process's
    # environment, so the plaintext never lands in the docker argv / `ps`.
    os.environ["DOS_API_TOKEN"] = api_token

    exec_args = ["docker", "exec", "-it",
                 "-e", "DOS_API_TOKEN", "-e", "IS_SANDBOX=1"]

    # Anthropic auth — by shell type (shells.api_auth, migration 014).
    #   api_auth=0 (CLI shell): no Anthropic env — `claude` browser-auths on
    #     first launch (subscription billing) and reaches Anthropic directly.
    #   api_auth=1 (API shell): point `claude` at the broker's /anthropic
    #     route. The broker holds the key and injects x-api-key on the way
    #     out — the key never enters the container. ANTHROPIC_AUTH_TOKEN is a
    #     non-secret placeholder: it satisfies Claude Code's "a credential is
    #     present" check (so it skips browser login) and the broker overrides
    #     it regardless. See shell_core/broker/README.md.
    if full["api_auth"]:
        exec_args += ["-e", f"ANTHROPIC_BASE_URL={BROKER_ANTHROPIC_URL}",
                      "-e", "ANTHROPIC_AUTH_TOKEN=broker-injected"]
        print("→ API shell — Anthropic routed through the broker")

    # Shells run with permission prompts off — the rootless-Docker container
    # IS the sandbox boundary, so prompting again inside it adds nothing.
    # `IS_SANDBOX=1` lets `--dangerously-skip-permissions` run as the
    # container's root user (Claude Code otherwise refuses that flag as root).
    exec_args += ["-w", "/workspace", container,
                  "claude", "--dangerously-skip-permissions"]
    os.execvp("docker", exec_args)


if __name__ == "__main__":
    main()
