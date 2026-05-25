#!/usr/bin/env python3
"""dr_sync — sync dr_* tables from the substrate's actual state.

Wired syncs:
  sync_routers_and_apis()
    Sources: shell_core/api/routers/*.py module docstrings (→ dr_router)
             FastAPI app.openapi() spec (→ dr_api, with router_id from tags)
    Idempotent: UPSERT keyed on dr_router.name and dr_api(path,method).

  sync_dependencies()
    Sources: shell_core/ui/package.json + node_modules/<pkg>/package.json
             (→ dr_dependencies, kind='npm', project='ui')
             importlib.metadata distributions in the running interpreter
             (→ dr_dependencies, kind='pip', project='substrate')
    Idempotent: UPSERT keyed on dr_dependencies(project, name).

Header-comment conventions (frontend):
  - `.js` files under `ui/src/lib/`: first `//` line at the top of the file
    is the summary. Recursive scan, so `lib/<subdir>/*.js` is in scope.
  - `.svelte` files under `ui/src/lib/components/`: first `//` line in the
    `<script>` block is the summary. Recursive scan; the file's location
    (path-relative-to-lib) is the dr_lib unique key.

Usage:
    python3 shell_core/scripts/dr_sync.py            # all syncs
    python3 shell_core/scripts/dr_sync.py apis       # apis + routers only
    python3 shell_core/scripts/dr_sync.py apis deps  # multiple targets
"""
import ast
import inspect
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "shell_core" / "shell_db.db"
ROUTERS_DIR = ROOT / "shell_core" / "api" / "routers"

DESCRIPTION_SHORT_CAP = 100


def _truncate(s: str, cap: int = DESCRIPTION_SHORT_CAP) -> str:
    s = (s or "").strip()
    return s if len(s) <= cap else s[: cap - 3] + "..."


def _homerel(p) -> str:
    """Store paths home-relative (~/...) so the catalogue is portable across
    users/machines. Absolute Path objects are kept for on-disk checks; only
    the stored string is relativized."""
    p = Path(p)
    try:
        return "~/" + str(p.relative_to(Path.home()))
    except ValueError:
        return str(p)


def _catalog_path(p) -> str:
    """Catalogue path string: repo-relative for files inside the repo, so the
    row is identical whether the sync runs from the host checkout (~/dos-arch)
    or the /substrate container mount. Home-relative for paths outside the
    repo. Absolute Path objects stay for on-disk checks — only the stored
    string is canonicalised."""
    p = Path(p)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return _homerel(p)


def _module_docstring_first_line(path: Path) -> str | None:
    """Parse the module's top-of-file docstring, return the first line."""
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return None
    doc = ast.get_docstring(tree)
    if not doc:
        return None
    return doc.strip().split("\n", 1)[0].strip()


def _reap(conn: sqlite3.Connection, table: str, id_col: str, seen_ids) -> int:
    """Retire active rows of a fully-rescanned surface whose row wasn't seen
    this run — the source entry is gone. Returns the count retired.

    A run that saw nothing reaps nothing: an empty scan is treated as a failed
    scan, not as 'every row was deleted'."""
    seen = list(seen_ids)
    if not seen:
        return 0
    placeholders = ",".join("?" * len(seen))
    cur = conn.execute(
        f"UPDATE {table} SET status = 'retired' "
        f"WHERE status = 'active' AND {id_col} NOT IN ({placeholders})",
        seen,
    )
    return cur.rowcount


def sync_routers_and_apis(conn: sqlite3.Connection, app=None) -> dict:
    """Walk shell_core/api/routers/*.py + FastAPI app.openapi().

    `app` may be passed in (e.g. from a FastAPI startup hook calling this
    in-process) to avoid the import of api.main. When omitted, we import
    api.main ourselves — fine for the CLI path.
    """
    if app is None:
        sys.path.insert(0, str(ROOT / "shell_core"))
        try:
            from api.main import app
        finally:
            sys.path.pop(0)

    counts = {
        "routers": {"insert": 0, "update": 0, "retire": 0},
        "apis":    {"insert": 0, "update": 0, "retire": 0},
    }
    seen_router_ids: list[int] = []
    seen_api_ids:    list[int] = []

    # ── dr_router rows ─────────────────────────────────────────────────────
    file_to_router_id: dict[str, int] = {}
    for f in sorted(ROUTERS_DIR.glob("*.py")):
        if f.name == "__init__.py":
            continue
        name = f.stem
        rel_path = str(f.relative_to(ROOT))
        desc = _truncate(_module_docstring_first_line(f) or f"FastAPI router: {name}")

        existing = conn.execute(
            "SELECT router_id FROM dr_router WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE dr_router SET description_short = ?, file_path = ?, "
                "last_verified = date('now') WHERE router_id = ?",
                (desc, rel_path, existing[0])
            )
            counts["routers"]["update"] += 1
            file_to_router_id[name] = existing[0]
        else:
            cur = conn.execute(
                "INSERT INTO dr_router (name, description_short, file_path, last_verified) "
                "VALUES (?, ?, ?, date('now'))",
                (name, desc, rel_path)
            )
            counts["routers"]["insert"] += 1
            file_to_router_id[name] = cur.lastrowid
        seen_router_ids.append(file_to_router_id[name])

    # ── dr_api rows from OpenAPI spec ──────────────────────────────────────
    spec = app.openapi()
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            method_u = method.upper()
            summary = _truncate(op.get("summary") or f"{method_u} {path}")
            description = op.get("description") or None
            tags = op.get("tags") or []
            router_id = next(
                (file_to_router_id[t] for t in tags if t in file_to_router_id),
                None
            )
            name = op.get("operationId") or f"{method}_{path}".replace("/", "_").strip("_")
            name = name[:100]

            existing = conn.execute(
                "SELECT api_id FROM dr_api WHERE path = ? AND method = ?",
                (path, method_u)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE dr_api SET name = ?, description_short = ?, purpose = ?, "
                    "router_id = ?, last_verified = date('now') WHERE api_id = ?",
                    (name, summary, description, router_id, existing[0])
                )
                counts["apis"]["update"] += 1
                seen_api_ids.append(existing[0])
            else:
                cur = conn.execute(
                    "INSERT INTO dr_api (router_id, name, description_short, path, method, "
                    "purpose, last_verified) VALUES (?, ?, ?, ?, ?, ?, date('now'))",
                    (router_id, name, summary, path, method_u, description)
                )
                counts["apis"]["insert"] += 1
                seen_api_ids.append(cur.lastrowid)

    counts["routers"]["retire"] = _reap(conn, "dr_router", "router_id", seen_router_ids)
    counts["apis"]["retire"]    = _reap(conn, "dr_api", "api_id", seen_api_ids)
    return counts


_PIP_MANIFESTS = [
    # (project, manifest_path_relative_to_ROOT)
    ("substrate", "shell_core/requirements.txt"),
    ("broker",    "shell_core/broker/requirements.txt"),
]


def _parse_requirements(path: Path) -> list[tuple[str, str]]:
    """Parse a pip requirements file → [(name, pin_or_empty)]. Ignores
    comments, blank lines, and `-r`/`-c` includes. Strips environment
    markers (`; python_version>='3.10'`) and extras (`pkg[foo]`)."""
    out: list[tuple[str, str]] = []
    if not path.exists():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Drop environment marker
        line = line.split(";", 1)[0].strip()
        # Split name and pin (==, >=, <=, ~=, >, <, !=)
        for op in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            if op in line:
                name, _, version = line.partition(op)
                out.append((name.strip().split("[", 1)[0], op + version.strip()))
                break
        else:
            out.append((line.split("[", 1)[0], ""))
    return out


def sync_dependencies(conn: sqlite3.Connection) -> dict:
    """Sync dr_dependencies from declared manifests:
      - shell_core/ui/package.json           → npm,  project='ui'
      - shell_core/requirements.txt          → pip,  project='substrate'
      - shell_core/broker/requirements.txt   → pip,  project='broker'

    Pip rows are enriched with version + summary from importlib.metadata
    when the package is installed in the current interpreter; unenriched
    rows still appear with the declared pin (or empty version).

    Idempotent: UPSERT keyed on (project, name). Rows whose declaration
    is gone from the manifests are retired via _reap.
    """
    counts = {"deps": {"insert": 0, "update": 0, "retire": 0}}
    seen_ids: list[int] = []

    def _upsert(project: str, name: str, kind: str, version: str, desc: str):
        existing = conn.execute(
            "SELECT dep_id FROM dr_dependencies WHERE project = ? AND name = ?",
            (project, name)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE dr_dependencies SET kind = ?, version = ?, description_short = ?, "
                "status = 'active' WHERE dep_id = ?",
                (kind, version, desc, existing[0])
            )
            counts["deps"]["update"] += 1
            seen_ids.append(existing[0])
        else:
            cur = conn.execute(
                "INSERT INTO dr_dependencies (project, name, kind, version, description_short) "
                "VALUES (?, ?, ?, ?, ?)",
                (project, name, kind, version, desc)
            )
            counts["deps"]["insert"] += 1
            seen_ids.append(cur.lastrowid)

    # ── NPM (UI project) ───────────────────────────────────────────────────
    ui_pkg_path = ROOT / "shell_core" / "ui" / "package.json"
    if ui_pkg_path.exists():
        node_modules = ROOT / "shell_core" / "ui" / "node_modules"
        try:
            pkg = json.loads(ui_pkg_path.read_text())
        except json.JSONDecodeError:
            pkg = {}
        for section in ("dependencies", "devDependencies"):
            for dep_name, dep_ver in (pkg.get(section) or {}).items():
                desc = None
                dep_pkg_json = node_modules / dep_name / "package.json"
                if dep_pkg_json.exists():
                    try:
                        desc = json.loads(dep_pkg_json.read_text()).get("description")
                    except (json.JSONDecodeError, OSError):
                        pass
                desc = _truncate(desc or f"npm package: {dep_name}")
                _upsert("ui", dep_name, "npm", dep_ver, desc)

    # ── pip (declared manifests; enriched from importlib.metadata) ─────────
    try:
        import importlib.metadata as importlib_metadata
        meta_index = {
            dist.metadata["Name"].lower(): dist
            for dist in importlib_metadata.distributions()
            if dist.metadata and dist.metadata["Name"]
        }
    except ImportError:
        meta_index = {}

    for project, rel_path in _PIP_MANIFESTS:
        for name, declared_pin in _parse_requirements(ROOT / rel_path):
            dist = meta_index.get(name.lower())
            if dist is not None:
                version = dist.version or declared_pin
                summary = (dist.metadata.get("Summary") if dist.metadata else None) \
                    or f"pip package: {name}"
            else:
                version = declared_pin
                summary = f"pip package: {name} (declared, not installed in current interpreter)"
            _upsert(project, name, "pip", version, _truncate(summary))

    counts["deps"]["retire"] = _reap(conn, "dr_dependencies", "dep_id", seen_ids)
    return counts


def sync_services(conn: sqlite3.Connection) -> dict:
    """Sync dr_services from ecosystem.config.cjs.

    Convention: each app in `module.exports.apps` carries a `summary` string
    (≤100 chars). pm2 ignores the field; the populator uses it for
    `description_short`. `kind` is inferred from `args` (uvicorn → api,
    vite → ui, else → other).

    Idempotent: UPSERT keyed on `name`.
    """
    import subprocess
    counts = {"services": {"insert": 0, "update": 0}}

    eco = ROOT / "ecosystem.config.cjs"
    if not eco.exists():
        return counts

    try:
        proc = subprocess.run(
            ["node", "-e", f"console.log(JSON.stringify(require({str(eco)!r})))"],
            capture_output=True, text=True, timeout=5
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return counts
    if proc.returncode != 0:
        return counts

    try:
        cfg = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return counts

    for app in cfg.get("apps", []):
        name = app.get("name")
        if not name:
            continue
        summary = _truncate(app.get("summary") or f"pm2 service: {name}")
        signal = f"{app.get('script') or ''} {app.get('args') or ''}"
        if "uvicorn" in signal:
            kind = "api"
        elif "vite" in signal:
            kind = "ui"
        else:
            kind = "other"
        location = app.get("cwd") or "./"

        existing = conn.execute(
            "SELECT service_id FROM dr_services WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE dr_services SET description_short = ?, kind = ?, location = ?, "
                "last_verified = date('now') WHERE service_id = ?",
                (summary, kind, location, existing[0])
            )
            counts["services"]["update"] += 1
        else:
            conn.execute(
                "INSERT INTO dr_services (name, description_short, kind, location, last_verified) "
                "VALUES (?, ?, ?, ?, date('now'))",
                (name, summary, kind, location)
            )
            counts["services"]["insert"] += 1

    return counts


def _join_comment_block(lines) -> str | None:
    """Collect contiguous `//` lines from `lines` (each already stripped),
    joining them with single spaces so a multi-line leading comment reads as
    one sentence. Blank lines before the first `//` are skipped; the block
    ends at the first non-comment line. Returns None if no `//` line was
    seen."""
    captured = []
    for s in lines:
        if not s:
            if captured:
                break  # blank line ends the block
            continue
        if s.startswith("//"):
            captured.append(s.lstrip("/").strip())
            continue
        break  # hit non-comment code
    if not captured:
        return None
    return " ".join(c for c in captured if c)


def _first_js_comment(text: str) -> str | None:
    """Leading `//` block at the top of a JS source. Multi-line comments are
    joined into one string."""
    return _join_comment_block(line.strip() for line in text.splitlines())


def _first_svelte_comment(text: str) -> str | None:
    """Leading `//` block inside the opening `<script>` of a .svelte file.
    Skips the `<script ...>` tag and any blank lines; joins multi-line
    comments."""
    inner = []
    in_script = False
    for line in text.splitlines():
        s = line.strip()
        if not in_script:
            if s.startswith("<script"):
                in_script = True
            continue
        inner.append(s)
    return _join_comment_block(inner) if inner else None


def sync_libs(conn: sqlite3.Connection) -> dict:
    """Sync dr_lib from backend (api/common/*.py) and frontend (ui/src/lib/
    recursive — .js helpers + .svelte components).

    Backend convention: top-of-file Python docstring, first line is the summary.
    Frontend convention: first `//` line at the top of the file (or inside the
    leading `<script>` block for .svelte). `name` is the path relative to the
    scan root, sans extension — so a top-level helper stays `api`, a sub-folder
    helper becomes `chat/models`, a component is `components/chat/ChatSidebar`.
    Idempotent: UPSERT keyed on (kind, location).
    """
    counts = {"libs": {"insert": 0, "update": 0, "retire": 0}}
    seen_ids: list[int] = []

    def _upsert(kind: str, name: str, location_path: Path, desc: str):
        rel = str(location_path.relative_to(ROOT))
        existing = conn.execute(
            "SELECT lib_id FROM dr_lib WHERE kind = ? AND location = ?", (kind, rel)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE dr_lib SET name = ?, description_short = ?, last_verified = date('now') "
                "WHERE lib_id = ?",
                (name, desc, existing[0])
            )
            counts["libs"]["update"] += 1
            seen_ids.append(existing[0])
        else:
            cur = conn.execute(
                "INSERT INTO dr_lib (kind, name, location, description_short, last_verified) "
                "VALUES (?, ?, ?, ?, date('now'))",
                (kind, name, rel, desc)
            )
            counts["libs"]["insert"] += 1
            seen_ids.append(cur.lastrowid)

    # ── Backend modules ────────────────────────────────────────────────────
    backend_dir = ROOT / "shell_core" / "api" / "common"
    if backend_dir.exists():
        for f in sorted(backend_dir.glob("*.py")):
            if f.name == "__init__.py":
                continue
            doc = _module_docstring_first_line(f)
            desc = _truncate(doc or f"backend module: {f.stem}")
            _upsert("backend", f.stem, f, desc)

    # ── Frontend: recursive .js + .svelte ──────────────────────────────────
    ui_lib_dir = ROOT / "shell_core" / "ui" / "src" / "lib"
    if ui_lib_dir.exists():
        def _name_from(f: Path) -> str:
            # path-relative-to-lib without extension — keeps subfolder helpers
            # unique (e.g. chat/models) and components disambiguated by path.
            return str(f.relative_to(ui_lib_dir).with_suffix(""))

        for f in sorted(ui_lib_dir.rglob("*.js")):
            comment = _first_js_comment(f.read_text())
            desc = _truncate(comment or f"frontend module: {_name_from(f)}")
            _upsert("frontend", _name_from(f), f, desc)

        for f in sorted(ui_lib_dir.rglob("*.svelte")):
            comment = _first_svelte_comment(f.read_text())
            desc = _truncate(comment or f"svelte component: {_name_from(f)}")
            _upsert("frontend", _name_from(f), f, desc)

    counts["libs"]["retire"] = _reap(conn, "dr_lib", "lib_id", seen_ids)
    return counts


def sync_repos(conn: sqlite3.Connection) -> dict:
    """Sync dr_repo for the substrate's own git origin.

    Pulls description from `gh repo view --json description,name` if `gh` is
    available; falls back to the repo's directory name. Future work: extend
    to a configured list of related repos via shells.connections or env.

    Idempotent: UPSERT keyed on `name`.
    """
    import subprocess
    counts = {"repos": {"insert": 0, "update": 0}}

    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return counts
    if proc.returncode != 0:
        return counts
    remote = proc.stdout.strip() or None

    name = ROOT.name
    desc = None
    try:
        gh_proc = subprocess.run(
            ["gh", "repo", "view", "--json", "description,name"],
            capture_output=True, text=True, timeout=5, cwd=str(ROOT)
        )
        if gh_proc.returncode == 0:
            data = json.loads(gh_proc.stdout)
            desc = data.get("description") or None
            name = data.get("name") or name
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass

    desc = _truncate(desc or f"git repo: {name}")

    existing = conn.execute("SELECT repo_id FROM dr_repo WHERE name = ?", (name,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE dr_repo SET description_short = ?, path = ?, remote = ?, "
            "last_verified = date('now') WHERE repo_id = ?",
            (desc, _homerel(ROOT), remote, existing[0])
        )
        counts["repos"]["update"] += 1
    else:
        conn.execute(
            "INSERT INTO dr_repo (name, description_short, path, remote, last_verified) "
            "VALUES (?, ?, ?, ?, date('now'))",
            (name, desc, _homerel(ROOT), remote)
        )
        counts["repos"]["insert"] += 1

    return counts


# ── Manually-curated typed registries ─────────────────────────────────────────
# The three surfaces below have no canonical machine-readable source. The
# entry lists in this file ARE the source-of-truth — adding a row means
# editing the corresponding list. The populator just keeps the DB in sync
# with the list (UPSERT keyed on the natural unique column).
#
# Why register them at all? So shells have a single place to look up
# "where is X / what env vars exist / what auto-runs" without grepping the
# whole codebase.

_FILEPATH_ENTRIES = [
    # (name, path, kind, description_short)
    ("schema",        ROOT / "shell_core" / "schema.sql",                "file", "Canonical SQLite schema (~25 tables + triggers + 2 catalogue views)"),
    ("shell_db",      ROOT / "shell_core" / "shell_db.db",               "file", "Live SQLite store — gitignored, local-only, bootstrap via make bootstrap"),
    ("catalog_template", ROOT / "shell_core" / "templates" / "catalog_universal.md", "file", "Baked universal catalog layer (Laws, Memory protocol, Communication) — render-chain input"),
    ("render_chain",  ROOT / "shell_core" / "shell_render.py",           "file", "Typed section catalog — assemble_catalog, the shared boot-prompt renderer"),
    ("launcher",      ROOT / "shell_core" / "scripts" / "run.py",        "file", "Auth → picker → render CLAUDE.md → exec claude"),
    ("dr_sync",       ROOT / "shell_core" / "scripts" / "dr_sync.py",    "file", "Catalogue populator — wired sync targets + dispatch"),
    ("bootstrap",     ROOT / "shell_core" / "scripts" / "bootstrap.py",  "file", "One-shot bootstrapper — schema + skills + Forge + first user + Sys-Admin"),
    ("db_init",       ROOT / "shell_core" / "scripts" / "db_init.py",    "file", "Seeding library — seed_skills / ensure_forge / seed_sys_admin"),
    ("create_user",   ROOT / "shell_core" / "scripts" / "create_user.py","file", "Provision a new substrate user with scrypt password"),
    ("set_password",  ROOT / "shell_core" / "scripts" / "set_password.py","file", "Reset a substrate user's scrypt password"),
    ("assets_dir",    ROOT / "shell_core" / "assets",                    "dir",  "Seed data — skills/*.md + shells/{forge,sys-admin}.md"),
    ("ecosystem",     ROOT / "ecosystem.config.cjs",                     "file", "pm2 process map — api on 8000, ui on 5173"),
    ("makefile",      ROOT / "Makefile",                                 "file", "Entry points: install, bootstrap, db-sync, db-backup, launch, up/down"),
    ("backups",       Path.home() / "db_backups" / "dos-arch",           "dir",  "Manual + boot DB snapshots (rolling-5 retention on boot snapshots)"),
    ("shared",        Path.home() / "shared",                            "dir",  "Host↔container shared root — per-shell scratch dirs, bind-mounted into shell containers"),
    ("global_claude", Path.home() / ".claude" / "CLAUDE.md",             "file", "Harness-injected universal preamble — laws, system override, shell selection"),
]


def sync_filepaths(conn: sqlite3.Connection) -> dict:
    """Sync curated dr_filepath entries from the static list above.

    Idempotent: UPSERT keyed on `path`. Entries whose path doesn't exist on
    disk are skipped — they may be on a host that doesn't have them (e.g.
    ~/shared on machines without the VM mount).
    """
    counts = {"filepaths": {"insert": 0, "update": 0, "retire": 0}}
    known_paths: set[str] = set()
    for name, path, kind, desc in _FILEPATH_ENTRIES:
        path_str = _catalog_path(path)
        known_paths.add(path_str)
        if not path.exists():
            continue
        existing = conn.execute(
            "SELECT filepath_id FROM dr_filepath WHERE path = ?", (path_str,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE dr_filepath SET name = ?, description_short = ?, kind = ?, "
                "last_verified = date('now') WHERE filepath_id = ?",
                (name, _truncate(desc), kind, existing[0])
            )
            counts["filepaths"]["update"] += 1
        else:
            conn.execute(
                "INSERT INTO dr_filepath (name, description_short, path, kind, last_verified) "
                "VALUES (?, ?, ?, ?, date('now'))",
                (name, _truncate(desc), path_str, kind)
            )
            counts["filepaths"]["insert"] += 1
    # Reap on entry-set membership, not per-run row visibility (unlike _reap).
    # A dr_filepath row is retired only when its path is no longer a curated
    # _FILEPATH_ENTRIES entry at all. A path the list still carries but this
    # execution context cannot see is kept: the dos-api container bind-mounts
    # only shell_core, so Makefile / ecosystem.config.cjs / ~/.claude are
    # absent there — a partial filesystem view must never retire entries that
    # are still curated. _catalog_path is context-independent, so `known_paths`
    # is the same set whether the sync runs from the host or the container.
    if known_paths:
        placeholders = ",".join("?" * len(known_paths))
        cur = conn.execute(
            f"UPDATE dr_filepath SET status = 'retired' "
            f"WHERE status = 'active' AND path NOT IN ({placeholders})",
            tuple(known_paths),
        )
        counts["filepaths"]["retire"] = cur.rowcount
    return counts


_AUTOMATION_ENTRIES = [
    # (name, trigger_kind, schedule, description_short)
    ("catalogue_startup_sync",  "api",     None,             "Refresh dr_* catalogue on FastAPI startup (api/main.py @on_event)"),
    ("dosarch-dr-sync.timer",   "systemd", "daily 04:00",    "Daily dr_* catalogue sync via systemd user timer (Persistent=true → catch-up on boot)"),
    ("boot_db_snapshot",        "manual",  "on make launch", "DB snapshot before each shell boot; rolling-5 retention in ~/db_backups/dos-arch"),
    ("missing_db_tripwire",     "manual",  "on make launch", "Abort launch if shell_db.db missing or 0 bytes; restore from snapshot"),
    ("forge_self_heal",         "manual",  "on make launch", "Re-seed Forge if missing from DB (run.py calls ensure_forge each boot)"),
]


def sync_automations(conn: sqlite3.Connection) -> dict:
    """Sync curated dr_automations entries — scheduled or trigger-driven jobs.
    Idempotent: UPSERT keyed on `name`. Rows absent from the curated list are
    retired via _reap."""
    counts = {"automations": {"insert": 0, "update": 0, "retire": 0}}
    seen_ids = []
    for name, kind, schedule, desc in _AUTOMATION_ENTRIES:
        existing = conn.execute(
            "SELECT automation_id FROM dr_automations WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE dr_automations SET description_short = ?, trigger_kind = ?, schedule = ?, "
                "status = 'active', last_verified = date('now') WHERE automation_id = ?",
                (_truncate(desc), kind, schedule, existing[0])
            )
            counts["automations"]["update"] += 1
            seen_ids.append(existing[0])
        else:
            cur = conn.execute(
                "INSERT INTO dr_automations (name, description_short, trigger_kind, schedule, last_verified) "
                "VALUES (?, ?, ?, ?, date('now'))",
                (name, _truncate(desc), kind, schedule)
            )
            counts["automations"]["insert"] += 1
            seen_ids.append(cur.lastrowid)
    counts["automations"]["retire"] = _reap(conn, "dr_automations", "automation_id", seen_ids)
    return counts


_ENV_ENTRIES = [
    # (name, scope, location, is_secret, description_short)

    # ── system / shell environment ────────────────────────────────────────
    ("ANTHROPIC_API_KEY",        "system",   "shell environment / ~/.bashrc",          1, "Anthropic API key — used by Claude Code CLI (rotated 2026-04-28 per CC-014)"),
    ("HOME",                     "system",   "OS standard",                            0, "User home dir — launcher resolves ~/db_backups/dos-arch and ~/.claude from this"),
    ("PATH",                     "system",   "OS standard",                            0, "Must include claude, gh, node, npm, pm2, python3 — see Dependencies in README"),

    # ── dotenv (~/.config/dos-arch/.env) — read host-side, never enters container ──
    ("OPENAI_API_KEY",           "dotenv",   "~/.config/dos-arch/.env",                1, "OpenAI API key — read by openai SDK + broker; required for GPT-* registry models"),
    ("GITHUB_TOKEN",             "dotenv",   "~/.config/dos-arch/.env",                1, "GitHub PAT — broker injects on git-over-HTTPS; lets shells clone/push credential-free"),

    # ── runtime (process-env knobs read at startup) ───────────────────────
    ("DR_SYNC_TRIGGER",          "runtime",  "systemd dosarch-dr-sync.service",        0, "Tag for dr_sync_runs row: cron/startup/manual (default manual)"),
    ("DOS_API_TOKEN",            "runtime",  "set per-session by scripts/run.py",      1, "Per-shell API token; minted by launcher and injected into the spawned process env"),

    # ── dispatcher tuning (shell_core/services/dispatch_live.py) ──────────
    ("DISPATCH_DB_PATH",         "runtime",  "shell_core/services/dispatch_live.py",   0, "Override DB path for dispatcher; default shell_core/shell_db.db"),
    ("DISPATCH_API_BASE",        "runtime",  "shell_core/services/dispatch_live.py",   0, "Override API base for dispatcher; default http://127.0.0.1:8001"),
    ("DISPATCH_MODEL",           "runtime",  "shell_core/services/dispatch_live.py",   0, "Fallback model when no per-shell choice set; default claude-sonnet-4-6"),
    ("DISPATCH_POOL_WORKERS",    "runtime",  "shell_core/services/dispatch_live.py",   0, "Concurrent worker count for the dispatch pool; default 5"),
    ("DISPATCH_TOOL_CONCURRENCY","runtime",  "shell_core/services/dispatch_live.py",   0, "Tool-call concurrency cap per dispatch run; default 20"),
    ("LOCAL_UNLOAD_SWEEP_SEC",   "runtime",  "shell_core/services/dispatch_live.py",   0, "Idle local-model unload sweep interval (seconds); default 30"),

    # ── Ollama integration (model_sync + provider adapter) ────────────────
    ("OLLAMA_HOST",              "runtime",  "shell_core/scripts/model_sync.py",       0, "Ollama daemon address for the model watcher; default 127.0.0.1:11434"),
    ("OLLAMA_API_BASE",          "runtime",  "shell_core/services/providers/ollama_adapter.py", 0, "Ollama API base for provider adapter; default derived from OLLAMA_HOST"),
    ("OLLAMA_NUM_CTX",           "runtime",  "shell_core/services/providers/ollama_adapter.py", 0, "Override Ollama context window size for chat completions"),
    ("OLLAMA_KEEP_ALIVE",        "runtime",  "shell_core/services/providers/ollama_adapter.py", 0, "Ollama model keep-alive duration (e.g. 30m, -1 for forever)"),
    ("MODEL_WATCH_INTERVAL",     "runtime",  "shell_core/scripts/model_sync.py",       0, "Model watcher polling interval (seconds); default 30"),
]


def sync_env(conn: sqlite3.Connection) -> dict:
    """Sync curated dr_env entries — env vars the substrate uses or expects.
    Values are NOT stored — registry only. Idempotent: UPSERT keyed on `name`.
    Rows absent from the curated list are retired via _reap."""
    counts = {"env": {"insert": 0, "update": 0, "retire": 0}}
    seen_ids: list[int] = []
    for name, scope, location, secret, desc in _ENV_ENTRIES:
        existing = conn.execute(
            "SELECT env_id FROM dr_env WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE dr_env SET description_short = ?, scope = ?, location = ?, is_secret = ?, "
                "status = 'active', last_verified = date('now') WHERE env_id = ?",
                (_truncate(desc), scope, location, secret, existing[0])
            )
            counts["env"]["update"] += 1
            seen_ids.append(existing[0])
        else:
            cur = conn.execute(
                "INSERT INTO dr_env (name, description_short, scope, location, is_secret, last_verified) "
                "VALUES (?, ?, ?, ?, ?, date('now'))",
                (name, _truncate(desc), scope, location, secret)
            )
            counts["env"]["insert"] += 1
            seen_ids.append(cur.lastrowid)
    counts["env"]["retire"] = _reap(conn, "dr_env", "env_id", seen_ids)
    return counts


SYNCS = {
    "apis":        sync_routers_and_apis,
    "deps":        sync_dependencies,
    "services":    sync_services,
    "libs":        sync_libs,
    "repos":       sync_repos,
    "filepaths":   sync_filepaths,
    "automations": sync_automations,
    "env":         sync_env,
}


def sync_all(conn: sqlite3.Connection, app=None) -> dict:
    """Run every sync in SYNCS. Functions that accept `app` get it; others don't.
    Per-sync exceptions are caught and surfaced in the result dict."""
    out: dict = {}
    for name, fn in SYNCS.items():
        try:
            kwargs = {}
            if "app" in inspect.signature(fn).parameters:
                kwargs["app"] = app
            out[name] = fn(conn, **kwargs)
        except Exception as e:
            out[name] = {"error": repr(e)}
    return out


def _record_run(conn, trigger_kind, results, fatal_error=None):
    """Write one dr_sync_runs row summarizing a sync invocation.

    `results` is the {target: counts} map — counts is {surface: {insert,update}}
    or the {"error": ...} shape sync_all uses for a whole-target failure.
    `fatal_error` is set when the run aborted before/around sync; it takes the
    error slot ahead of any per-surface error. The error column is truncated to
    100 chars so a too-long message never makes this logging insert itself fail.
    """
    total_ins = total_upd = 0
    first_err = fatal_error
    for target, counts in (results or {}).items():
        if isinstance(counts, dict) and "error" in counts:
            if first_err is None:
                first_err = f"{target}: {counts['error']}"
            continue
        for surface, c in (counts or {}).items():
            if "error" in c:
                if first_err is None:
                    first_err = f"{surface}: {c['error']}"
            else:
                total_ins += c.get("insert", 0)
                total_upd += c.get("update", 0)
    conn.execute(
        "INSERT INTO dr_sync_runs (run_at, trigger_kind, surfaces, total_insert, "
        "total_update, had_error, error) VALUES (datetime('now'), ?, ?, ?, ?, ?, ?)",
        (trigger_kind, json.dumps(results or {}), total_ins, total_upd,
         1 if first_err else 0, _truncate(first_err) if first_err else None),
    )


def main() -> int:
    # 'cron' when invoked by the scheduled host sync (it sets DR_SYNC_TRIGGER);
    # 'manual' for an interactive `make db-sync` / direct CLI run.
    trigger_kind = os.environ.get("DR_SYNC_TRIGGER", "manual")
    targets = sys.argv[1:] or list(SYNCS.keys())
    unknown = [t for t in targets if t not in SYNCS]
    if unknown:
        print(f"Unknown sync target(s): {unknown}. Known: {list(SYNCS)}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB_PATH)
    results: dict = {}
    rc = 0
    try:
        for target in targets:
            fn = SYNCS[target]
            kwargs = {}
            if "app" in inspect.signature(fn).parameters:
                kwargs["app"] = None  # CLI path: let fn self-import
            try:
                counts = fn(conn, **kwargs)
            except Exception as e:  # mirror sync_all — one bad target never aborts the run
                counts = {"error": repr(e)}
            results[target] = counts
            print(f"[{target}]")
            if "error" in counts:
                print(f"  ERROR {counts['error']}")
                rc = 1
            else:
                for surface, c in counts.items():
                    if "error" in c:
                        print(f"  {surface}: ERROR {c['error']}")
                        rc = 1
                    else:
                        print(f"  {surface}: {c['insert']} inserted, {c['update']} updated, {c.get('retire', 0)} retired")
        _record_run(conn, trigger_kind, results)
        conn.commit()
    except Exception as e:
        # Catastrophic failure (DB, commit, etc.) — still try to leave a row.
        print(f"dr_sync FAILED: {e!r}", file=sys.stderr)
        try:
            _record_run(conn, trigger_kind, results, fatal_error=repr(e))
            conn.commit()
        except Exception:
            pass
        rc = 1
    finally:
        conn.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
