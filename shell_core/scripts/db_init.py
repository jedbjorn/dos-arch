#!/usr/bin/env python3
"""Substrate seeding library.

Seeds a substrate DB from the tracked assets in `shell_core/assets/`:

    assets/skills/*.md      one file per skill  (frontmatter + body)
    assets/shells/forge.md  the shared bootstrap shell
    assets/shells/sys-admin.md  the resident admin/dev shell (template-rendered)

This module is a library, not a script. The full one-shot entry point is
`bootstrap.py` (`make bootstrap`). The launcher (`run.py`) imports
`ensure_forge` and calls it on every boot, so a DB missing Forge self-heals.

All seed functions are INSERT-missing-only — they never UPDATE existing
rows, so local edits to the live DB survive a re-run. Propagating an
*update* to an existing row is a migration's job, not a seeder's.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from shared_dirs import ensure_shared_dirs

ROOT        = Path(__file__).resolve().parents[2]
ASSETS      = ROOT / "shell_core" / "assets"
SKILLS_DIR  = ASSETS / "skills"
SHELLS_DIR  = ASSETS / "shells"
TEMPLATE    = ROOT / "shell_core" / "templates" / "shell_system_prompt.md"


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
    """INSERT every skill in assets/skills/ that isn't already present.
    Returns the names of newly-seeded skills. Caller commits."""
    seeded: list[str] = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        meta, body = parse_frontmatter(path.read_text())
        name = meta["name"]
        if con.execute("SELECT 1 FROM skills WHERE name=?", (name,)).fetchone():
            continue
        con.execute(
            "INSERT INTO skills (name, description, category, content, command, common) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, meta.get("description", ""), meta.get("category", "workflow"),
             body, meta.get("command") or None, int(meta.get("common", "0"))),
        )
        seeded.append(name)
    return seeded


# ── Models registry + tools (agnostic-runtime §4.1-§4.2) ──────────────────────

# The model registry. A1 ships Anthropic + OpenAI; Gemini / local land with
# CC-51. context_window / max_output / cost_* stay NULL until their consumers
# (compaction CC-52/53, cost accounting) need them — A1 reads only
# name / provider / tool_dialect / auth_ref / status.
#   (name, display_name, provider, auth_ref, tool_dialect)
_MODELS = [
    ("claude-opus-4-7",           "Claude Opus 4.7",   "anthropic", "ANTHROPIC_API_KEY", "anthropic"),
    ("claude-sonnet-4-6",         "Claude Sonnet 4.6", "anthropic", "ANTHROPIC_API_KEY", "anthropic"),
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5",  "anthropic", "ANTHROPIC_API_KEY", "anthropic"),
    ("gpt-5",                     "GPT-5",             "openai",    "OPENAI_API_KEY",    "openai"),
]

# The api_* tool surface — get/post/patch/delete against the system's own API
# (agnostic-runtime §5.4). The dispatcher loads these from `tools` rather than
# a hard-coded list. `spec` is the JSON-Schema parameter object; each
# ProviderAdapter projects it onto its provider's tool dialect.
_PATH_PROP = {
    "type": "string",
    "description": 'API path including query, must start with /. e.g. "/shells/2/decisions"',
}
#   (name, description, spec)
_API_TOOLS = [
    ("api_get",
     "GET request to the dos-arch API. Path may include a query string. "
     "Returns the response body as text.",
     {"type": "object", "properties": {"path": _PATH_PROP}, "required": ["path"]}),
    ("api_post",
     "POST request to the dos-arch API. Body sent as JSON.",
     {"type": "object",
      "properties": {"path": {"type": "string"},
                     "body": {"type": "object", "description": "JSON body."}},
      "required": ["path", "body"]}),
    ("api_patch",
     "PATCH request to the dos-arch API. Body sent as JSON.",
     {"type": "object",
      "properties": {"path": {"type": "string"}, "body": {"type": "object"}},
      "required": ["path", "body"]}),
    ("api_delete",
     "DELETE request to the dos-arch API. Optional JSON body.",
     {"type": "object",
      "properties": {"path": {"type": "string"},
                     "body": {"type": "object", "description": "Optional JSON body."}},
      "required": ["path"]}),
]


def seed_models(con: sqlite3.Connection) -> list[str]:
    """INSERT every registry model not already present (matched by name).
    Returns the names newly seeded. Caller commits."""
    seeded: list[str] = []
    for name, display, provider, auth_ref, dialect in _MODELS:
        if con.execute("SELECT 1 FROM models WHERE name=?", (name,)).fetchone():
            continue
        con.execute(
            "INSERT INTO models (name, display_name, provider, auth_ref, "
            "tool_dialect, locality, status) "
            "VALUES (?, ?, ?, ?, ?, 'remote', 'active')",
            (name, display, provider, auth_ref, dialect),
        )
        seeded.append(name)
    return seeded


def seed_tools(con: sqlite3.Connection) -> list[str]:
    """INSERT every api_* tool not already present, then grant every active
    tool to every shell (a shell's tool set is the shell_tools join).
    Returns the names newly seeded. Caller commits."""
    seeded: list[str] = []
    for name, description, spec in _API_TOOLS:
        if con.execute("SELECT 1 FROM tools WHERE name=?", (name,)).fetchone():
            continue
        con.execute(
            "INSERT INTO tools (name, description, kind, spec, handler, status) "
            "VALUES (?, ?, 'builtin', ?, 'api', 'active')",
            (name, description, json.dumps(spec)),
        )
        seeded.append(name)
    # Grant every active tool to every shell — INSERT OR IGNORE dedups.
    con.execute(
        "INSERT OR IGNORE INTO shell_tools (shell_id, tool_id) "
        "SELECT s.shell_id, t.tool_id FROM shells s CROSS JOIN tools t "
        "WHERE t.status='active'"
    )
    return seeded


def ensure_forge(con: sqlite3.Connection) -> tuple[int, bool]:
    """Idempotently seed Forge (the shared bootstrap shell) from
    assets/shells/forge.md. Returns (forge_shell_id, created).

    Also called by `run.py` on every boot — a DB missing Forge self-heals.
    Skills are seeded first so Forge's attachment resolves.
    """
    existing = con.execute(
        "SELECT shell_id FROM shells WHERE shortname='forge' AND is_shared=1"
    ).fetchone()
    if existing:
        return existing[0], False

    seed_skills(con)

    meta, prompt = parse_frontmatter((SHELLS_DIR / "forge.md").read_text())
    cur = con.execute(
        "INSERT INTO shells (display_name, shortname, mandate, additional_prompt, "
        "has_identity, is_shared) VALUES (?, ?, ?, ?, 1, ?)",
        (meta["display_name"], meta["shortname"], meta.get("mandate"),
         prompt, int(meta.get("is_shared", "0"))),
    )
    forge_id = cur.lastrowid
    _attach_skills(con, forge_id, meta.get("skills", ""))
    ensure_shared_dirs(forge_id, meta["shortname"])
    return forge_id, True


def seed_sys_admin(con: sqlite3.Connection, user_id: int) -> tuple[int, bool]:
    """Seed the resident admin/dev shell, owned by `user_id`. Returns
    (shell_id, created). The additional_prompt is rendered from the canonical
    template, with the two domain sections supplied by sys-admin.md."""
    meta, body = parse_frontmatter((SHELLS_DIR / "sys-admin.md").read_text())
    shortname = meta["shortname"]

    existing = con.execute(
        "SELECT shell_id FROM shells WHERE shortname=?", (shortname,)
    ).fetchone()
    if existing:
        return existing[0], False

    domain, _, operating = body.partition("## OPERATING CONTEXT")
    domain = domain.replace("## DOMAIN & SCOPE", "").strip()
    operating = operating.strip()

    additional_prompt = (TEMPLATE.read_text()
        .replace("{{DISPLAY_NAME}}", meta["display_name"])
        .replace("{{SHORTNAME}}", shortname)
        .replace("{{FLAG_PREFIX}}", shortname.upper())
        .replace("{{DOMAIN_AND_SCOPE}}", domain)
        .replace("{{OPERATING_CONTEXT}}", operating))
    if "{{" in additional_prompt:
        raise ValueError("unfilled template slot in sys-admin render")

    username = con.execute(
        "SELECT username FROM users WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    # is_admin=1 — Sys-Admin is the substrate's one admin shell; its API key
    # carries the admin scope. Worker shells created later default to 0.
    cur = con.execute(
        "INSERT INTO shells (display_name, shortname, partner, role, mandate, "
        "additional_prompt, user_id, is_shared, is_admin) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1)",
        (meta["display_name"], shortname, username, meta.get("role"),
         meta.get("mandate"), additional_prompt, user_id),
    )
    sa_id = cur.lastrowid
    _attach_skills(con, sa_id, meta.get("skills", ""))
    ensure_shared_dirs(sa_id, shortname)
    return sa_id, True
