"""Shared section renderers for the shell boot-prompt render chain.

A shell's boot prompt is rendered from live DB state by two paths:

  * ``shell_core/scripts/run.py`` — the CLI launcher. Writes the rendered
    prompt to ``shells/<shortname>/CLAUDE.md`` for an interactive ``claude``.
  * ``shell_core/api/services/boot_document.py`` — the API path. Materializes
    ``chat_sessions.boot_document`` for the dispatcher (local / API-model shells).

Both compose from the *same* DB state, and several sections — identity,
seed, L&S, skills — were rendered by byte-identical copy-pasted functions in
each file. This module is the single home for those shared section
renderers: a change to how a section renders now lands once, not once per
renderer. ``assemble_catalog`` goes further — it composes the full
17-section typed catalog (spec §02), section order and all, from the
per-section renderers below; the two render paths converge on it as each
is cut over. Each section header carries a `kind` tag (`protocol` /
`identity` / `state` / `capability`) so the shell can orient at a glance.

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
    """One-sentence role anchor + markdown table of the shell's identity
    columns. The anchor binds shell + FnB names up front so weaker models
    cannot drift on who-is-who before reaching the table. Empty cells render '—'."""
    def cell(v: object) -> str:
        s = v.strip() if isinstance(v, str) else (v or "")
        return str(s) if s else "—"
    name = cell(shell_row['display_name'])
    partner = cell(shell_row['partner'])
    anchor = (
        f"you are {name}, an AI shell. your FnB partner is {partner}, "
        "a human collaborator. the substrate gives you persistent memory, "
        "tools, skills, and context for the work you do together."
    )
    return (
        f"{anchor}\n\n"
        "| | |\n"
        "|---|---|\n"
        f"| **Name** | {name} |\n"
        f"| **Shortname** | {cell(shell_row['shortname'])} |\n"
        f"| **Partner** | {partner} |\n"
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
# built from. Sections cluster by `kind` — protocol (rules) → identity (what
# you are) → state (what's true now) → capability (what you can call) — with
# PROHIBITIONS + LAWS tail-anchored after the capability cluster so the
# hardest constraints stay last-read. `assemble_catalog` composes all
# seventeen; the per-section renderers above and below it are the building
# blocks.
#
# The DB-driven sections render from live shell state. The baked universal
# sections — Definitions, Memory protocol, Prohibitions, Laws, Communication
# — come from templates/catalog_universal.md via `render_universal`. The
# Tools section is dialect-shaped (spec §05) via `render_tools`; the output
# shape is dialect-shaped via `render_output_shape` and appended to the
# COMMUNICATION body at composition time (no standalone section).

RECENT_DECISIONS_N = 3   # Section K — most-recent decisions rendered (spec open Q#2)

# The baked universal layer — sections identical for every shell (spec §02).
_UNIVERSAL_PATH = Path(__file__).resolve().parent / "templates" / "catalog_universal.md"
_UNIVERSAL_MARKER = re.compile(r"^<!-- @@ (\w+) @@ -->$")


def render_universal() -> dict[str, str]:
    """Parse the baked universal layer (`templates/catalog_universal.md`) into
    its section bodies, keyed by marker: SYSTEM_OVERRIDE, DEFINITIONS,
    MEMORY_PROTOCOL, PROHIBITIONS, LAWS, COMMUNICATION. These sections are
    identical for every shell (spec §02); the file is their single source of
    truth."""
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


def write_universal_block(key: str, body: str) -> None:
    """Rewrite a single `<!-- @@ KEY @@ -->` block in catalog_universal.md,
    preserving the file's header comment, marker lines, and every other block
    exactly. The new body is sandwiched as: marker line, blank line, stripped
    body, blank line, then the next marker (or EOF). Raises ValueError if KEY
    is unknown."""
    text = _UNIVERSAL_PATH.read_text()
    lines = text.splitlines()
    target_idx = None
    next_idx = len(lines)
    for i, line in enumerate(lines):
        m = _UNIVERSAL_MARKER.match(line)
        if not m:
            continue
        if m.group(1) == key:
            target_idx = i
        elif target_idx is not None:
            next_idx = i
            break
    if target_idx is None:
        raise ValueError(f"unknown universal block: {key}")
    new_body = body.strip()
    # File convention: marker line, body lines, single blank line, next marker.
    # No blank between marker and body. Final block has no trailing blank.
    rebuilt = (
        lines[: target_idx + 1]
        + (new_body.splitlines() if new_body else [])
        + ([""] if next_idx < len(lines) else [])
        + lines[next_idx:]
    )
    # Preserve trailing newline if the original had one.
    out = "\n".join(rebuilt)
    if text.endswith("\n") and not out.endswith("\n"):
        out += "\n"
    _UNIVERSAL_PATH.write_text(out)


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
    """Section D — projects the shell inherits from its owning user.

    Visibility is derived, not stored (docs/core-data-model.md): a shell has no
    project rows of its own — it sees the projects its user has *joined* via
    user_projects (shell → shells.user_id → user_projects → projects)."""
    rows = con.execute(
        "SELECT p.shortname, p.purpose, p.status FROM projects p "
        "JOIN user_projects up ON up.project_id = p.project_id "
        "WHERE up.user_id = (SELECT user_id FROM shells WHERE shell_id=?) "
        "AND up.is_deleted=0 AND COALESCE(p.is_deleted,0)=0 "
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
    return f"{n} open. Invoke `--flags` to surface."


# Section E — the tools this shell can call: general tools (is_general=1,
# every shell) plus the shell's directly-granted tools (shell_tools — which
# include the tools materialised from each skill the shell holds). The same
# effective set the dispatcher's `load_tools()` resolves, so the prompt and
# the runtime cannot disagree on what the shell can call. The general tools
# are generic HTTP verbs against the substrate API; which path is a seed / a
# decision / a flag — that map is in MEMORY PROTOCOL (section G).


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
    """Section E — the shell's tools, shaped by tool dialect (spec §05). A tool
    is general (is_general=1 — every shell) or granted to the shell via
    shell_tools; granted tools group under the skill that requires them (or
    "granted directly" when no held skill does), general tools render first.
    `anthropic` / `openai`: a name + description roster — the provider applies
    each tool's schema. `parsed`: each tool with its params and a worked
    `<tool:…>` invocation, for a local model that forms the call as text."""
    rows = con.execute(
        "SELECT t.name, t.description, t.spec, t.is_general, "
        "  (SELECT s.name FROM skill_tools kt "
        "     JOIN skills s ON s.skill_id = kt.skill_id "
        "     JOIN shell_skills ss ON ss.skill_id = kt.skill_id AND ss.shell_id = ? "
        "    WHERE kt.tool_id = t.tool_id ORDER BY s.name LIMIT 1) AS skill_name "
        "FROM tools t "
        "WHERE t.status='active' "
        "  AND (t.is_general=1 "
        "       OR t.tool_id IN (SELECT tool_id FROM shell_tools WHERE shell_id=?)) "
        "ORDER BY (t.is_general=0), (skill_name IS NULL), skill_name, t.tool_id",
        (shell_id, shell_id),
    ).fetchall()
    if not rows:
        return "(none granted)"
    general = [r for r in rows if r["is_general"]]
    skilled = [r for r in rows if not r["is_general"]]

    if dialect == "parsed":
        out = [
            "# parsed dialect — the runtime applies no tool schema. Form each",
            "# call in this format; the harness extracts and executes it. The",
            "# endpoint paths are in MEMORY PROTOCOL.",
            "",
        ]
        last = None
        for r in rows:
            group = "general" if r["is_general"] else (r["skill_name"] or "granted directly")
            if group != last:
                out.append(f"## {group}")
                last = group
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
    # is enough. General tools first, then each granted skill's own tools.
    out = ["# the provider applies each tool's schema — this is the roster."]
    if general:
        out.append("# general — substrate API verbs; endpoint paths in MEMORY PROTOCOL.")
        out += [f"- **{r['name']}** — {r['description']}" for r in general]
    last = None
    for r in skilled:
        if r["skill_name"] != last:
            out.append(f"# {r['skill_name']} (skill)" if r["skill_name"]
                       else "# granted directly")
            last = r["skill_name"]
        out.append(f"- **{r['name']}** — {r['description']}")
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


def prompt_sections(
    con: sqlite3.Connection,
    shell_id: int,
    *,
    dialect: str = "anthropic",
    runtime_ctx: dict,
) -> list[tuple[str, str, str, str]]:
    """The typed (label, body, scope, kind) catalog (spec §02) for a shell, in
    render order. Sections cluster by `kind` — `protocol` → `identity` → `state`
    → `capability`, with PROHIBITIONS and LAWS tail-anchored after the
    capability cluster so the hardest constraints stay last-read.

    `scope` is "universal" for sections whose body is shared across all shells
    (same body fans out to every shell — edits propagate) and "shell" for
    sections derived from this shell's identity, assignments, or runtime.

    `kind` is the shell-facing orientation tag rendered into each section
    header by `assemble_catalog` (`## LABEL · kind ##`) — `protocol` (rules),
    `identity` (what you are), `state` (what's true now), `capability` (what
    you can call). The taxonomy is the shell's, not the renderer's: it tells
    the model which mental bucket a section's bytes belong to.

    OUTPUT SHAPE is dialect-shaped but is no longer a standalone section — it
    is appended to COMMUNICATION's body as an `**output shape**` subsection so
    "how to communicate" reads as one whole.

    Pure read — same composition path as `assemble_catalog`; the viewer reads
    structure straight from this list."""
    shell = con.execute(
        "SELECT display_name, shortname, partner, role, mandate, "
        "current_state, connections FROM shells WHERE shell_id=?",
        (shell_id,),
    ).fetchone()
    if shell is None:
        raise ValueError(f"shell {shell_id} not found")
    universal = render_universal()

    communication = (
        universal["COMMUNICATION"]
        + "\n\n**output shape**\n"
        + render_output_shape(dialect)
    )

    return [
        # protocol — universal rules that bind every shell.
        ("SYSTEM OVERRIDE",   universal["SYSTEM_OVERRIDE"],          "universal", "protocol"),
        ("DEFINITIONS",       universal["DEFINITIONS"],              "universal", "protocol"),
        ("MEMORY PROTOCOL",   universal["MEMORY_PROTOCOL"],          "universal", "protocol"),
        ("COMMUNICATION",     communication,                         "universal", "protocol"),
        # identity — stable facts about this shell.
        ("IDENTITY",          render_identity(shell),                "shell",     "identity"),
        ("OPERATING CONTEXT", render_operating_context(shell),       "shell",     "identity"),
        ("SEED",              render_seed(con, shell_id),            "shell",     "identity"),
        ("LESSONS & STANCES", render_lns(con, shell_id),             "shell",     "identity"),
        # state — what's true right now for this shell.
        ("BOOT",              render_boot_context(runtime_ctx),      "shell",     "state"),
        ("CURRENT STATE",     render_current_state(shell),           "shell",     "state"),
        ("ACTIVE PROJECTS",   render_active_projects(con, shell_id), "shell",     "state"),
        ("RECENT DECISIONS",  render_recent_decisions(con, shell_id),"shell",     "state"),
        ("OPEN FLAGS",        render_flags_pointer(con, shell_id),   "shell",     "state"),
        # capability — what this shell can reach for.
        ("TOOLS",             render_tools(con, shell_id, dialect),  "shell",     "capability"),
        ("SKILLS AVAILABLE",  render_skills(con, shell_id),          "shell",     "capability"),
        # tail constraints — last-read so recency keeps them honoured.
        ("PROHIBITIONS",      universal["PROHIBITIONS"],             "universal", "protocol"),
        ("LAWS",              universal["LAWS"],                     "universal", "protocol"),
    ]


def assemble_catalog(
    con: sqlite3.Connection,
    shell_id: int,
    *,
    dialect: str = "anthropic",
    runtime_ctx: dict,
) -> str:
    """Compose the full typed boot-prompt catalog (spec §02) for a shell.
    Sections cluster by kind (protocol → identity → state → capability) with
    PROHIBITIONS + LAWS tail-anchored; each section header carries its kind
    tag as `## LABEL · kind ##`. Pure read.

    `runtime_ctx` carries the render-time values a DB query cannot give —
    wall-clock, session ids; see `render_boot_context`. The baked universal
    sections come from `catalog_universal.md`; `dialect` shapes the Tools
    section and the output-shape subsection of COMMUNICATION.

    Both render paths compose through it — `compose_claude_md` (the CLI
    launcher) and `compose_boot_document` (the API)."""
    sections = prompt_sections(
        con, shell_id, dialect=dialect, runtime_ctx=runtime_ctx,
    )
    return "\n\n".join(
        f"## {label} · {kind} ##\n{body}" for label, body, _scope, kind in sections
    )
