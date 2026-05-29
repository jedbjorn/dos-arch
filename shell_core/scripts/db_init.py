#!/usr/bin/env python3
"""Substrate seeding library.

Seeds a substrate DB from the tracked assets in `shell_core/assets/`.

Most domains follow the manifest convention (see the `asset_seeding`
skill): a directory `assets/<domain>/` holds a `_seed.toml` contract plus
one `*.md` per row, and `seed_from_assets` drives the INSERT — the schema
is the type authority, the manifest names the destination, the files are
rows. Skills and tools seed this way.

    assets/skills/   _seed.toml + one *.md per skill
    assets/tools/    _seed.toml + one *.md per tool (body = JSON spec)

Shells are the documented exception — `ensure_forge` / `seed_exp_prime`
stay bespoke because they need boot-time values (the first user's id, a
rendered template, skill attachment) an asset file can't carry. Models
stay an inline literal (`_MODELS`) — a small, stable set.

This module is a library, not a script. The full one-shot entry point is
`bootstrap.py` (`make bootstrap`), which calls `ensure_forge` to seed Forge.

All seed functions are INSERT-missing-only — they never UPDATE existing
rows, so local edits to the live DB survive a re-run. Propagating an
*update* to an existing row is a migration's job, not a seeder's.
"""
from __future__ import annotations

import json
import sqlite3
import tomllib
from pathlib import Path

from shared_dirs import ensure_shared_dirs

ROOT        = Path(__file__).resolve().parents[2]
ASSETS      = ROOT / "shell_core" / "assets"
SHELLS_DIR  = ASSETS / "shells"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a `---` delimited frontmatter block from the body.

    Frontmatter is single-line `key: value` pairs. The body may itself
    contain `---` lines (markdown rules) — only the first closing `---`
    delimits the frontmatter.
    """
    if not text.startswith("---\n"):
        raise ValueError("missing frontmatter")
    rest = text[4:]
    end = rest.find("\n---\n")
    if end == -1:
        raise ValueError("unterminated frontmatter")
    meta: dict[str, str] = {}
    for line in rest[:end].splitlines():
        line = line.strip()
        if not line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, rest[end + 5:]


def _coerce(value: str, decl_type: str):
    """Coerce a frontmatter string to a column's declared SQLite type.
    Frontmatter is always text; the schema's `PRAGMA table_info` type is
    the authority. An empty value becomes NULL."""
    if value == "":
        return None
    t = decl_type.upper()
    if "INT" in t:
        return int(value)
    if any(k in t for k in ("REAL", "FLOA", "DOUB")):
        return float(value)
    return value


def seed_from_assets(con: sqlite3.Connection, domain: str) -> list[str]:
    """Seed one asset domain — `assets/<domain>/` — into its table.

    The domain's `_seed.toml` is the contract:

        table        target table
        match        column used for INSERT-missing-only dedup
        body         column the markdown / JSON body is written to
        body_format  optional — 'text' (default) or 'json' (validated at seed)
        [const]      optional — column = value pairs applied to every row

    Each `*.md` file is one row: frontmatter keys map 1:1 to columns, the
    body goes to the `body` column. Every key — manifest, const, and
    frontmatter — is checked against the live schema (`PRAGMA table_info`);
    an unknown column, a missing match key, or a body that fails
    `body_format` validation is a hard error. INSERT-missing-only; returns
    the match values newly seeded. Caller commits.
    """
    domain_dir = ASSETS / domain
    manifest_path = domain_dir / "_seed.toml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"{domain}: missing {manifest_path}")
    manifest = tomllib.loads(manifest_path.read_text())

    table       = manifest["table"]
    match       = manifest["match"]
    body_col    = manifest["body"]
    body_format = manifest.get("body_format", "text")
    const       = manifest.get("const", {})

    if body_format not in ("text", "json"):
        raise ValueError(f"{domain}: unknown body_format '{body_format}'")
    cols = {row[1]: row[2] for row in con.execute(f"PRAGMA table_info({table})")}
    if not cols:
        raise ValueError(f"{domain}: table '{table}' not in schema")
    for col in (match, body_col, *const):
        if col not in cols:
            raise ValueError(
                f"{domain}: _seed.toml names column '{col}' not on table '{table}'")

    seeded: list[str] = []
    for path in sorted(domain_dir.glob("*.md")):
        meta, body = parse_frontmatter(path.read_text())
        for key in meta:
            if key not in cols:
                raise ValueError(
                    f"{path.name}: frontmatter key '{key}' is not a column on '{table}'")
        if match not in meta:
            raise ValueError(f"{path.name}: missing match key '{match}' in frontmatter")
        if body_format == "json":
            try:
                json.loads(body)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path.name}: body is not valid JSON — {e}") from e

        if con.execute(
            f"SELECT 1 FROM {table} WHERE {match}=?", (meta[match],)
        ).fetchone():
            continue

        row = {**const,
               **{k: _coerce(v, cols[k]) for k, v in meta.items()},
               body_col: body}
        con.execute(
            f"INSERT INTO {table} ({', '.join(row)}) "
            f"VALUES ({', '.join('?' for _ in row)})",
            tuple(row.values()),
        )
        seeded.append(meta[match])
    return seeded


def _attach_skills(con: sqlite3.Connection, shell_id: int, spec: str) -> None:
    """Attach skills to a shell. `spec` is a comma-separated list of skill
    names; the token `common` expands to every `common=1` skill. Mixing is
    allowed — e.g. `common, database-migrations` gives the baseline set plus
    that named extra (INSERT OR IGNORE dedups any overlap)."""
    ids: list[int] = []
    for token in (s.strip() for s in spec.split(",") if s.strip()):
        if token == "common":
            ids += [r[0] for r in con.execute(
                "SELECT skill_id FROM skills WHERE common=1 AND is_deleted=0")]
        else:
            row = con.execute("SELECT skill_id FROM skills WHERE name=?", (token,)).fetchone()
            if row:
                ids.append(row[0])
    con.executemany(
        "INSERT OR IGNORE INTO shell_skills (shell_id, skill_id) VALUES (?, ?)",
        [(shell_id, sid) for sid in ids],
    )


def seed_skills(con: sqlite3.Connection) -> list[str]:
    """INSERT every skill in `assets/skills/` not already present (matched
    by name). Returns the names newly seeded. Caller commits."""
    return seed_from_assets(con, "skills")


# ── Models registry (agnostic-runtime §4.1) ──────────────────────────────────

# The remote model registry. context_window is seeded — the browser-chat token
# meter reads it; max_output / cost_* stay NULL until their consumers (cost
# accounting) need them.
#   (name, display_name, provider, auth_ref, tool_dialect, locality, endpoint, context_window)
# Model names verified live against each provider's models.list() — keep them
# current; a stale name is a hard 404 at call time.
#
# Local models are NOT seeded here. model_sync.py is the source of truth for
# them: it reads Ollama's installed set via /api/tags + /api/show on every
# tick, UPSERTs each into the `models` registry as a provider='local' row,
# sets supports_tools + accepts_substrate_system from /api/show, and flips
# inactive any row whose model is no longer installed. A fresh install with
# no Ollama starts with zero local rows — they appear when the operator
# installs Ollama, pulls a model, and `make sync-models` (or the
# `dosarch-modelsync` pm2 watcher) lands the live row.
_MODELS = [
    ("claude-opus-4-7",           "Claude Opus 4.7",   "anthropic", "ANTHROPIC_API_KEY", "anthropic", "remote", None, 200_000),
    ("claude-sonnet-4-6",         "Claude Sonnet 4.6", "anthropic", "ANTHROPIC_API_KEY", "anthropic", "remote", None, 200_000),
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5",  "anthropic", "ANTHROPIC_API_KEY", "anthropic", "remote", None, 200_000),
    ("gpt-5.5",                   "GPT-5.5",           "openai",    "OPENAI_API_KEY",    "openai",    "remote", None, 128_000),
    ("gpt-5.5-pro",               "GPT-5.5 Pro",       "openai",    "OPENAI_API_KEY",    "openai",    "remote", None, 128_000),
    ("gpt-5.4-mini",              "GPT-5.4 Mini",      "openai",    "OPENAI_API_KEY",    "openai",    "remote", None, 128_000),
]


def seed_models(con: sqlite3.Connection) -> list[str]:
    """INSERT every registry model not already present (matched by name).
    Returns the names newly seeded. Caller commits."""
    seeded: list[str] = []
    for name, display, provider, auth_ref, dialect, locality, endpoint, ctx_window in _MODELS:
        if con.execute("SELECT 1 FROM models WHERE name=?", (name,)).fetchone():
            continue
        con.execute(
            "INSERT INTO models (name, display_name, provider, auth_ref, "
            "tool_dialect, locality, endpoint, context_window, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
            (name, display, provider, auth_ref, dialect, locality, endpoint, ctx_window),
        )
        seeded.append(name)
    return seeded


def seed_tools(con: sqlite3.Connection) -> list[str]:
    """INSERT every tool in `assets/tools/` not already present, then scope
    each skill-bound tool to its skill via the [skill_map] table in the tools
    seed manifest. Entries without a dot are handler-family prefixes
    (`file` matches `file.*`, scoping the whole family to one skill). Entries
    with a dot are exact handler matches, used when one family splits across
    skills (`flag.create` vs `flag.resolve`). A tool whose handler matches
    nothing in the map stays general (skill_id NULL — the api_* verbs).
    Returns the names newly seeded. Caller commits. Tools need no per-shell
    grant — a general tool is universal, a skill-bound tool comes with its
    skill."""
    seeded = seed_from_assets(con, "tools")
    skill_map = tomllib.loads(
        (ASSETS / "tools" / "_seed.toml").read_text()).get("skill_map", {})
    for key, skill_name in skill_map.items():
        row = con.execute(
            "SELECT skill_id FROM skills WHERE name=? AND is_deleted=0",
            (skill_name,),
        ).fetchone()
        if not row:
            continue
        if "." in key:
            con.execute(
                "UPDATE tools SET skill_id=? WHERE skill_id IS NULL AND handler=?",
                (row[0], key),
            )
        else:
            con.execute(
                "UPDATE tools SET skill_id=? WHERE skill_id IS NULL AND handler LIKE ?",
                (row[0], key + ".%"),
            )
    return seeded


def ensure_forge(con: sqlite3.Connection) -> tuple[int, bool]:
    """Idempotently seed Forge (the shared bootstrap shell) from
    assets/shells/forge.md. Returns (forge_shell_id, created).

    Skills are seeded first so Forge's attachment resolves.
    """
    existing = con.execute(
        "SELECT shell_id FROM shells WHERE shortname='forge' AND is_shared=1"
    ).fetchone()
    if existing:
        return existing[0], False

    seed_skills(con)

    # forge.md: frontmatter → identity columns; body → connections (the
    # catalog's Operating Context section). No template, no additional_prompt.
    meta, body = parse_frontmatter((SHELLS_DIR / "forge.md").read_text())
    cur = con.execute(
        "INSERT INTO shells (display_name, shortname, mandate, connections, "
        "has_identity, is_shared) VALUES (?, ?, ?, ?, 1, ?)",
        (meta["display_name"], meta["shortname"], meta.get("mandate"),
         body.strip(), int(meta.get("is_shared", "0"))),
    )
    forge_id = cur.lastrowid
    _attach_skills(con, forge_id, meta.get("skills", ""))
    ensure_shared_dirs(forge_id, meta["shortname"])
    return forge_id, True


def seed_exp_prime(con: sqlite3.Connection, user_id: int) -> tuple[int, bool]:
    """Seed Exp-Prime — the standardized assistant shell, owned by `user_id`.
    Returns (shell_id, created). exp-prime.md's frontmatter carries the identity
    columns; its body is the shell's connections (catalog Operating Context).

    This is the resident shell on a fresh substrate, replacing the former
    Sys-Admin. It is NOT a dev/admin shell: substrate administration is owned
    externally by the sysadmin, so is_admin=0. It is web-facing (browser-chat +
    dispatcher), so api_auth=1 routes it through the credential broker, which
    Anthropic's ToS requires for any shell backing a web app."""
    meta, body = parse_frontmatter((SHELLS_DIR / "exp-prime.md").read_text())
    shortname = meta["shortname"]

    existing = con.execute(
        "SELECT shell_id FROM shells WHERE shortname=?", (shortname,)
    ).fetchone()
    if existing:
        return existing[0], False

    username = con.execute(
        "SELECT username FROM users WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    # is_admin=0 — no in-substrate admin shell; the sysadmin administers the
    # substrate externally. api_auth=1 — web-facing shell, broker-routed per
    # Anthropic ToS. browser_chat=1 — chat-enabled from cold boot, so the
    # dispatcher (started by `make up`) serves it immediately with no
    # post-install activation step.
    cur = con.execute(
        "INSERT INTO shells (display_name, shortname, partner, role, mandate, "
        "connections, user_id, is_shared, is_admin, api_auth, browser_chat) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 1, 1)",
        (meta["display_name"], shortname, username, meta.get("role"),
         meta.get("mandate"), body.strip(), user_id),
    )
    ep_id = cur.lastrowid
    _attach_skills(con, ep_id, meta.get("skills", ""))
    ensure_shared_dirs(ep_id, shortname)
    return ep_id, True
