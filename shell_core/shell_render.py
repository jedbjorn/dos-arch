"""Shared section renderers for the shell boot-prompt render chain.

A shell's boot prompt is rendered from live DB state by two paths:

  * ``shell_core/scripts/run.py`` — the CLI launcher. Writes the rendered
    prompt to ``shells/<shortname>/CLAUDE.md`` for an interactive ``claude``.
  * ``shell_core/api/services/boot_document.py`` — the API path. Materializes
    ``shells.boot_document`` for the dispatcher (local / API-model shells).

Both compose from the *same* DB state, and several sections — identity,
seed, L&S, skills — were rendered by byte-identical copy-pasted functions in
each file. This module is the single home for those shared section
renderers: a change to how a section renders now lands once, not once per
renderer. ``assemble_catalog`` goes further — it composes the full
16-section typed catalog (spec §02), section order and all, from the
per-section renderers below; the two render paths converge on it as each
is cut over.

This is the seam the shell-prompt-renderer spec (§01) builds the typed
section catalog on — keep new shared section renderers here.

Importable from both contexts: the API runs with ``shell_core/`` on
``PYTHONPATH`` (``PYTHONPATH=/substrate/shell_core``); ``run.py`` puts the
same directory on ``sys.path`` before importing this module.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path


def render_identity(shell_row: sqlite3.Row) -> str:
    """Markdown table of the shell's identity columns. Empty cells render '—'."""
    def cell(v: object) -> str:
        s = v.strip() if isinstance(v, str) else (v or "")
        return str(s) if s else "—"
    return (
        "| | |\n"
        "|---|---|\n"
        f"| **Name** | {cell(shell_row['display_name'])} |\n"
        f"| **Shortname** | {cell(shell_row['shortname'])} |\n"
        f"| **Partner** | {cell(shell_row['partner'])} |\n"
        f"| **Role** | {cell(shell_row['role'])} |\n"
        f"| **Mandate** | {cell(shell_row['mandate'])} |"
    )


def render_seed(con: sqlite3.Connection, shell_id: int) -> str:
    """The shell's live seed entries, oldest first, each headed by its date."""
    rows = con.execute(
        "SELECT entry_date, body FROM shell_identity_entries "
        "WHERE shell_id=? AND kind='seed' AND is_deleted=0 AND retired_at IS NULL "
        "ORDER BY entry_date, entry_id",
        (shell_id,),
    ).fetchall()
    if not rows:
        return "(none)"
    return "\n\n".join(f"### {r['entry_date']}\n{r['body']}" for r in rows)


def render_lns(con: sqlite3.Connection, shell_id: int) -> str:
    """The shell's live Lessons & Stances entries, oldest first."""
    rows = con.execute(
        "SELECT body FROM shell_identity_entries "
        "WHERE shell_id=? AND kind='lns' AND is_deleted=0 AND retired_at IS NULL "
        "ORDER BY entry_date, entry_id",
        (shell_id,),
    ).fetchall()
    if not rows:
        return "(none)"
    return "\n\n".join(r["body"] for r in rows)


def render_skills(con: sqlite3.Connection, shell_id: int) -> str:
    """The shell's granted skills as a name + first-line-of-description list."""
    rows = con.execute(
        "SELECT s.name, s.description FROM skills s "
        "JOIN shell_skills ss ON ss.skill_id = s.skill_id "
        "WHERE ss.shell_id=? AND s.is_deleted=0 ORDER BY s.name",
        (shell_id,),
    ).fetchall()
    if not rows:
        return "(none)"
    lines = []
    for r in rows:
        desc = (r["description"] or "").strip().splitlines()[0] if r["description"] else ""
        lines.append(f"- **{r['name']}** — {desc}")
    return "\n".join(lines)


# ── Typed section catalog (shell-prompt-renderer spec §02) ────────────────────
#
# The catalog is the ordered set of sections every rendered boot prompt is
# built from — identity frames first, constraints (Laws, Communication) sit
# last where recency keeps them honoured. `assemble_catalog` composes all
# sixteen; the per-section renderers above and below it are the building
# blocks.
#
# The DB-driven sections render from live shell state. The baked universal
# sections — Memory protocol, Laws, Communication — come from
# templates/catalog_universal.md via `render_universal`. The Tools and Output
# Shape sections are dialect-shaped (spec §05) — `render_tools` /
# `render_output_shape`. `assemble_catalog` is not yet called by either
# render path.

RECENT_DECISIONS_N = 3   # Section K — most-recent decisions rendered (spec open Q#2)

# The baked universal layer — sections identical for every shell (spec §02).
_UNIVERSAL_PATH = Path(__file__).resolve().parent / "templates" / "catalog_universal.md"
_UNIVERSAL_MARKER = re.compile(r"^<!-- @@ (\w+) @@ -->$")


def render_universal() -> dict[str, str]:
    """Parse the baked universal layer (`templates/catalog_universal.md`) into
    its section bodies, keyed by marker: SYSTEM_OVERRIDE, MEMORY_PROTOCOL,
    LAWS, COMMUNICATION. These sections are identical for every shell
    (spec §02); the file is their single source of truth."""
    blocks: dict[str, list[str]] = {}
    key: str | None = None
    for line in _UNIVERSAL_PATH.read_text().splitlines():
        marker = _UNIVERSAL_MARKER.match(line)
        if marker:
            key = marker.group(1)
            blocks[key] = []
        elif key is not None:
            blocks[key].append(line)
    return {k: "\n".join(v).strip() for k, v in blocks.items()}


def render_boot_context(runtime_ctx: dict) -> str:
    """Section ⌂ — wall-clock + session metadata, computed by the caller at
    render time. A local model has no clock, so this section is its only one.
    `runtime_ctx` keys: `datetime` (a datetime), `session_id`, `archive_id`,
    `shell_id`, and optional `model` / `operator`. `operator` names who is
    driving the session — a shared shell (Forge) needs it to know who to
    assign a newly-created shell to."""
    dt = runtime_ctx["datetime"]
    model = runtime_ctx.get("model") or "—"
    line2 = f"shell_id: {runtime_ctx['shell_id']} · model: {model}"
    if runtime_ctx.get("operator"):
        line2 += f" · operator: {runtime_ctx['operator']}"
    return (
        f"session: {runtime_ctx['session_id']} · archive: {runtime_ctx['archive_id']} · "
        f"date: {dt:%Y-%m-%d (%A)} · {dt:%H:%M} local\n"
        f"{line2}"
    )


def render_operating_context(shell_row: sqlite3.Row) -> str:
    """Section B — where the shell runs: repos, paths, services, conventions.
    Straight from `shells.connections`."""
    return (shell_row["connections"] or "").strip() or "(none)"


def render_domain_scope(shell_row: sqlite3.Row) -> str:
    """Section C — the shell's role and mandate, from the shell row."""
    role = (shell_row["role"] or "").strip()
    mandate = (shell_row["mandate"] or "").strip()
    return f"role: {role or '—'}\nmandate: {mandate or '—'}"


def render_active_projects(con: sqlite3.Connection, shell_id: int) -> str:
    """Section D — the shell's non-deleted project assignments."""
    rows = con.execute(
        "SELECT p.shortname, p.purpose, p.status FROM projects p "
        "JOIN project_shells ps ON ps.project_id = p.project_id "
        "WHERE ps.shell_id=? AND ps.is_deleted=0 AND COALESCE(p.is_deleted,0)=0 "
        "ORDER BY p.shortname",
        (shell_id,),
    ).fetchall()
    if not rows:
        return "None currently assigned."
    lines = []
    for r in rows:
        purpose = (r["purpose"] or "").strip() or "(no purpose set)"
        lines.append(f"- {r['shortname']} · {purpose} · status: {r['status'] or 'active'}")
    return "\n".join(lines)


def render_current_state(shell_row: sqlite3.Row) -> str:
    """Section H — the shell's rolling now/next status."""
    return (shell_row["current_state"] or "").strip() or "(none)"


def render_recent_decisions(con: sqlite3.Connection, shell_id: int) -> str:
    """Section K — the most recent decisions, newest first (spec §02: top N)."""
    rows = con.execute(
        "SELECT decision_date, priority, decision, rationale FROM shell_decisions "
        "WHERE shell_id=? AND COALESCE(is_deleted,0)=0 "
        "ORDER BY decision_date DESC, decision_id DESC LIMIT ?",
        (shell_id, RECENT_DECISIONS_N),
    ).fetchall()
    if not rows:
        return "(none recorded yet)"
    out = []
    for r in rows:
        line = f"[{r['decision_date']}] {r['priority']} · {r['decision']}"
        if (r["rationale"] or "").strip():
            line += f"\nrationale: {r['rationale'].strip()}"
        out.append(line)
    return "\n".join(out)


def render_flags_pointer(con: sqlite3.Connection, shell_id: int) -> str:
    """Section L — a count of open flags, never the flags themselves. The
    flag-triage skill does the actual read (spec §03)."""
    n = con.execute(
        "SELECT COUNT(*) FROM flags "
        "WHERE shell_id=? AND resolved=0 AND COALESCE(is_deleted,0)=0",
        (shell_id,),
    ).fetchone()[0]
    if not n:
        return "0 open."
    return f"{n} open. Invoke `--flag-triage` to surface."


# Section E — the tools this shell can call. Read from the `tools` ⋈
# `shell_tools` grant — the same source the dispatcher's `load_tools()` uses,
# so the prompt and the runtime cannot disagree on what the shell can call.
# The substrate API is the whole tool surface; these are generic HTTP verbs
# against it. Which path is a seed / a decision / a flag — that map is in
# MEMORY PROTOCOL (section G).


def _spec_params(spec: str | None) -> list[str]:
    """Rendered param lines from a tool's JSON-schema `spec` — for the parsed
    dialect, where the local model forms the call as text."""
    try:
        schema = json.loads(spec) if spec else {}
    except (json.JSONDecodeError, TypeError):
        return []
    required = set(schema.get("required", []))
    lines = []
    for name, prop in (schema.get("properties") or {}).items():
        typ = prop.get("type", "?")
        req = "required" if name in required else "optional"
        note = prop.get("description", "")
        lines.append(f"  {name:<6} {typ:<8} {req}" + (f"  {note}" if note else ""))
    return lines


def render_tools(con: sqlite3.Connection, shell_id: int,
                 dialect: str = "anthropic") -> str:
    """Section E — the shell's granted tools (`tools` ⋈ `shell_tools`), shaped
    by tool dialect (spec §05). `anthropic` / `openai`: a name + description
    roster — the provider applies each tool's schema. `parsed`: each tool with
    its params and a worked `<tool:…>` invocation, for a local model that
    forms the call as text."""
    rows = con.execute(
        "SELECT t.name, t.description, t.spec FROM tools t "
        "JOIN shell_tools st ON st.tool_id = t.tool_id "
        "WHERE st.shell_id=? AND t.status='active' ORDER BY t.tool_id",
        (shell_id,),
    ).fetchall()
    if not rows:
        return "(none granted)"

    if dialect == "parsed":
        out = [
            "# parsed dialect — the runtime applies no tool schema. Form each",
            "# call in this format; the harness extracts and executes it. The",
            "# endpoint paths are in MEMORY PROTOCOL.",
            "",
        ]
        for r in rows:
            out.append(f"**{r['name']}** — {r['description']}")
            params = _spec_params(r["spec"])
            if params:
                out.append("params:")
                out += params
            out.append("")
        out += [
            "invoke (example):",
            "  <tool:api_post>",
            "  path: /shells/<self>/decisions",
            '  body: {"decision": "...", "rationale": "..."}',
            "  </tool>",
            "",
            "If you cannot form a valid call, say so plainly:",
            "  i can't do this yet — i'm missing {what}",
        ]
        return "\n".join(out)

    # anthropic / openai — the provider applies each tool's schema; a roster
    # is enough. The substrate API is the surface; paths are in MEMORY PROTOCOL.
    out = ["# the provider applies each tool's schema — this is the roster.",
           "# the substrate API is the surface; endpoint paths are in MEMORY PROTOCOL."]
    out += [f"- **{r['name']}** — {r['description']}" for r in rows]
    return "\n".join(out)


def render_output_shape(dialect: str = "anthropic") -> str:
    """Section O — how to address the operator and emit tool calls, shaped by
    dialect (spec §02, §05)."""
    if dialect == "parsed":
        return (
            "Respond to the operator in plaintext. The runtime applies no tool "
            "schema — form each call yourself in the `<tool:name> … </tool>` "
            "format shown in TOOLS, and the harness extracts it. If you cannot "
            "form a valid call, say so plainly rather than emit a malformed one."
        )
    if dialect == "openai":
        return (
            "Respond to the operator in plain markdown. Tool calls use the "
            "OpenAI function-call schema — the runtime parses them; you never "
            "hand-format a call. Keep plaintext between tool calls."
        )
    return (
        "Respond to your partner in plain GitHub-flavored markdown. Tool calls "
        "use the harness's native tool schema — the provider applies it; you "
        "never hand-format a call. Keep plaintext between tool calls."
    )


def assemble_catalog(
    con: sqlite3.Connection,
    shell_id: int,
    *,
    dialect: str = "anthropic",
    runtime_ctx: dict,
) -> str:
    """Compose the full typed boot-prompt catalog (spec §02) for a shell — a
    SYSTEM OVERRIDE preamble followed by the ⌂/A–O sections. Pure read.

    `runtime_ctx` carries the render-time values a DB query cannot give —
    wall-clock, session ids; see `render_boot_context`. The baked universal
    sections come from `catalog_universal.md`; `dialect` shapes the Tools and
    Output Shape sections.

    Not yet wired into either render path — `compose_claude_md` and
    `compose_boot_document` are cut over to it in later slices."""
    shell = con.execute(
        "SELECT display_name, shortname, partner, role, mandate, "
        "current_state, connections FROM shells WHERE shell_id=?",
        (shell_id,),
    ).fetchone()
    if shell is None:
        raise ValueError(f"shell {shell_id} not found")
    universal = render_universal()

    # ⌂ then A–O, in catalog order (spec §02).
    sections = [
        ("BOOT",              render_boot_context(runtime_ctx)),
        ("IDENTITY",          render_identity(shell)),
        ("OPERATING CONTEXT", render_operating_context(shell)),
        ("DOMAIN & SCOPE",    render_domain_scope(shell)),
        ("ACTIVE PROJECTS",   render_active_projects(con, shell_id)),
        ("TOOLS",             render_tools(con, shell_id, dialect)),
        ("SKILLS AVAILABLE",  render_skills(con, shell_id)),
        ("MEMORY PROTOCOL",   universal["MEMORY_PROTOCOL"]),
        ("CURRENT STATE",     render_current_state(shell)),
        ("SEED",              render_seed(con, shell_id)),
        ("LESSONS & STANCES", render_lns(con, shell_id)),
        ("RECENT DECISIONS",  render_recent_decisions(con, shell_id)),
        ("OPEN FLAGS",        render_flags_pointer(con, shell_id)),
        ("LAWS",              universal["LAWS"]),
        ("COMMUNICATION",     universal["COMMUNICATION"]),
        ("OUTPUT SHAPE",      render_output_shape(dialect)),
    ]
    catalog = "\n\n".join(f"## {label} ##\n{body}" for label, body in sections)
    return f"## SYSTEM OVERRIDE ##\n{universal['SYSTEM_OVERRIDE']}\n\n{catalog}"
