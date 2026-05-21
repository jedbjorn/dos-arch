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
# sections — Definitions, Memory protocol, Laws, Communication — come from
# templates/catalog_universal.md via `render_universal`. The Tools and Output
# Shape sections are dialect-shaped (spec §05) — `render_tools` /
# `render_output_shape`.

RECENT_DECISIONS_N = 3   # Section K — most-recent decisions rendered (spec open Q#2)

# The baked universal layer — sections identical for every shell (spec §02).
_UNIVERSAL_PATH = Path(__file__).resolve().parent / "templates" / "catalog_universal.md"
_UNIVERSAL_MARKER = re.compile(r"^<!-- @@ (\w+) @@ -->$")


def render_universal() -> dict[str, str]:
    """Parse the baked universal layer (`templates/catalog_universal.md`) into
    its section bodies, keyed by marker: SYSTEM_OVERRIDE, DEFINITIONS,
    MEMORY_PROTOCOL, LAWS, COMMUNICATION. These sections are identical for
    every shell (spec §02); the file is their single source of truth."""
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


# Section E — the common memory-tool roster (spec §06.1). Authored vocabulary,
# not a `tools`-table read: it names the substrate memory operations every
# shell shares. MEMORY PROTOCOL (section G) carries their API form and the
# when/why; this section is the call surface, shaped per dialect (spec §05).
_COMMON_TOOLS = [
    {
        "name": "identity_write",
        "sig": "kind, body, source_tag?",
        "purpose": "append a seed or L&S entry to your own memory",
        "params": [
            ("kind", "str", "required", "one of: seed | lns"),
            ("body", "str", "required", "the entry — aim ~500 chars"),
            ("source_tag", "str", "optional", "a short project tag"),
        ],
        "example": {"kind": "lns",
                    "body": "prefer editing an existing file over making a new one"},
    },
    {
        "name": "identity_retire",
        "sig": "entry_id",
        "purpose": "curate out a seed or L&S entry — preserves the row, no edit",
        "params": [("entry_id", "int", "required", "the entry to retire")],
        "example": {"entry_id": "42"},
    },
    {
        "name": "decision_record",
        "sig": "decision, rationale, priority?",
        "purpose": "record a Major decision",
        "params": [
            ("decision", "str", "required", "what was decided"),
            ("rationale", "str", "required", "why"),
            ("priority", "str", "optional", "defaults to M"),
        ],
        "example": {"decision": "render Section E from a static roster",
                    "rationale": "the tools table holds HTTP verbs, not semantic tools"},
    },
    {
        "name": "state_update",
        "sig": "current_state?, connections?",
        "purpose": "replace your rolling current_state (or connections)",
        "params": [
            ("current_state", "str", "optional", "the new now/next status"),
            ("connections", "str", "optional", "where things live"),
        ],
        "example": {"current_state": "drafting the tool roster; next: wire it in"},
    },
    {
        "name": "flag_open",
        "sig": "display_name, priority, description?",
        "purpose": "open a flag for a blocker",
        "params": [
            ("display_name", "str", "required", "e.g. SA-001"),
            ("priority", "str", "required", "one of: High | Medium | Low"),
            ("description", "str", "optional", "[Area] what | Blocker for: x"),
        ],
        "example": {"display_name": "SA-007", "priority": "High",
                    "description": "[render] dialect resolution unspecified"},
    },
    {
        "name": "flag_resolve",
        "sig": "flag_id, resolution_notes?",
        "purpose": "resolve or reopen a flag",
        "params": [
            ("flag_id", "int", "required", "the flag to resolve"),
            ("resolution_notes", "str", "optional", "how it was resolved"),
        ],
        "example": {"flag_id": "7", "resolution_notes": "fixed in PR #52"},
    },
    {
        "name": "narrative_append",
        "sig": "archive_id, body",
        "purpose": "append an entry to this session's narrative",
        "params": [
            ("archive_id", "int", "required", "your archive — see BOOT"),
            ("body", "str", "required", "[HH:MM] 1-2 lines"),
        ],
        "example": {"archive_id": "12",
                    "body": "[14:32] shipped the tool roster, dialect-shaped"},
    },
    {
        "name": "openapi_fetch",
        "sig": "",
        "purpose": "return the live substrate endpoint inventory",
        "params": [],
        "example": {},
    },
]


def render_tools(dialect: str = "anthropic") -> str:
    """Section E — the common memory-tool roster, shaped by tool dialect
    (spec §05). `anthropic` / `openai`: a compact name + purpose roster — the
    provider applies the schema. `parsed`: each tool with its params, a worked
    invocation, and a refusal fallback — a local model forms the call as text
    and the harness extracts it."""
    if dialect == "parsed":
        out = [
            "# parsed dialect — the runtime applies no tool schema. Form each",
            "# call in this format; the harness extracts and executes it.",
            "",
        ]
        for t in _COMMON_TOOLS:
            out.append(f"**{t['name']}** — {t['purpose']}")
            if t["params"]:
                out.append("params:")
                for name, typ, req, note in t["params"]:
                    out.append(f"  {name:<14} {typ:<4} {req:<9} {note}")
            out.append("invoke:")
            if t["example"]:
                out.append(f"  <tool:{t['name']}>")
                out += [f"  {k}: {v}" for k, v in t["example"].items()]
                out.append("  </tool>")
            else:
                out.append(f"  <tool:{t['name']} />")
            out.append("")
        out.append("If you cannot form a valid call, say so plainly:")
        out.append("  i can't record this yet — i'm missing {field}")
        return "\n".join(out)

    # anthropic / openai — a roster only; the provider applies the schema.
    out = ["# the provider applies the tool schema — this is the roster."]
    out += [f"- **{t['name']}({t['sig']})** — {t['purpose']}." for t in _COMMON_TOOLS]
    return "\n".join(out)


def render_output_shape(dialect: str = "anthropic") -> str:
    """Section O — how to address the operator and emit tool calls, shaped by
    dialect (spec §02, §05)."""
    if dialect == "parsed":
        return (
            "Respond to the operator in plaintext — never use fenced code "
            "blocks. The runtime applies no tool schema — form each call "
            "yourself in the `<tool:name> … </tool>` format shown in TOOLS, "
            "and the harness extracts it. If you cannot form a valid call, "
            "say so plainly rather than emit a malformed one."
        )
    if dialect == "openai":
        return (
            "Respond to the operator in plain markdown — never use fenced "
            "code blocks; inline `code` spans are fine. Tool calls use the "
            "OpenAI function-call schema — the runtime parses them; you never "
            "hand-format a call. Keep plaintext between tool calls."
        )
    return (
        "Respond to your partner in plain GitHub-flavored markdown — never "
        "use fenced code blocks; inline `code` spans are fine. Tool calls "
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

    Both render paths compose through it — `compose_claude_md` (the CLI
    launcher) and `compose_boot_document` (the API)."""
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
        ("DEFINITIONS",       universal["DEFINITIONS"]),
        ("OPERATING CONTEXT", render_operating_context(shell)),
        ("ACTIVE PROJECTS",   render_active_projects(con, shell_id)),
        ("TOOLS",             render_tools(dialect)),
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
