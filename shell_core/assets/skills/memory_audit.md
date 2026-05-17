---
name: memory_audit
description: Audit what is loaded into context at session start — flat files, DB fields, token estimate, redundancy, stale local files.
category: workflow
common: 1
command: -memory audit
---
# memory_audit

- **skill_id:** 16
- **category:** workflow
- **common:** 0
- **description:** Audit what is loaded into context at session start — flat files, DB fields, token estimate, redundancy, stale local files.

---

# Memory Audit Skill

Trigger: owner says "memory audit", "audit memory", "redundancy check", or asks what's loaded at session start.

Two checks:
1. **Redundancy** — data that appears in both the rendered per-shell `CLAUDE.md` AND somewhere else also loaded at boot. Redundant loads burn tokens.
2. **Stale local files** — files on disk that aren't referenced anywhere in `CLAUDE.md`. Orphans.

DB path: `/path/to/dos-arch/shell_core/shell_db.db`. Use python3 + sqlite3 module (no CLI on host — see `db_map`).

---

## Step 1 — What's loaded at boot

Three flat files arrive in context every session:

| File | What it carries |
|---|---|
| `~/.claude/CLAUDE.md` | Universal pointer (no content — directs to `make run`) |
| `/path/to/dos-arch/CLAUDE.md` | Substrate project instructions (cwd-loaded) |
| `/path/to/dos-arch/shells/cc/CLAUDE.md` | Per-shell rendered file — assembled by `run.py` from DB at session start |

Measure each:
```python
import os
for p in ['~/.claude/CLAUDE.md',
          '/path/to/dos-arch/CLAUDE.md',
          '/path/to/dos-arch/shells/cc/CLAUDE.md']:
    print(f"{p}: {os.path.getsize(p)} bytes" if os.path.exists(p) else f"{p}: MISSING")
```

The per-shell file is assembled directly from these DB pieces (no intermediate payload column — `session_payload` was retired in PR #17):

- `shells.system_prompt` → IDENTITY / DEFINITIONS / MEMORY ARCHITECTURE / WRITES / CLOSE / FLAGS
- `shells.current_state` → CURRENT STATE block
- `shell_identity_entries WHERE kind='seed'` (active) → SEED block
- `shell_identity_entries WHERE kind='lns'` (active) → LESSONS & STANCES block
- `projects ⋈ project_shells` (active) → ACTIVE PROJECTS block
- `shell_core/templates/boot.md` → SYSTEM OVERRIDE + LAWS
- Skills block from `shell_skills ⋈ skills` (name + description only)

Pull DB-side sizes:
```python
import sqlite3
con = sqlite3.connect('/path/to/dos-arch/shell_core/shell_db.db')
r = con.execute("""SELECT length(system_prompt) sp, length(connections) conn,
                          length(current_state) cs
                   FROM shells WHERE shell_id=1""").fetchone()
print(f"system_prompt={r[0]} connections={r[1]} current_state={r[2]}")

print("identity entries (active):")
for k, n, ch in con.execute("""SELECT kind, COUNT(*), SUM(length(body))
                               FROM shell_identity_entries
                               WHERE shell_id=1 AND is_deleted=0 AND retired_at IS NULL
                               GROUP BY kind"""):
    print(f"  {k}: {n} entries / {ch} chars")
```

## Step 2 — Redundancy check

For the current architecture, the render path is single-chain (DB rows → `run.py` → per-shell `CLAUDE.md`):

| Surface (DB) | Renders into | Redundant? |
|---|---|---|
| `shells.system_prompt` | per-shell `CLAUDE.md` SYSTEM PROMPT block | source-only — not re-loaded |
| `shells.current_state` | per-shell `CLAUDE.md` CURRENT STATE block | source-only — not re-loaded |
| `shell_identity_entries` | per-shell `CLAUDE.md` SEED + L&S blocks | source-only — not re-loaded |
| `projects` ⋈ `project_shells` | per-shell `CLAUDE.md` ACTIVE PROJECTS block | source-only — not re-loaded |
| `templates/boot.md` (LAWS + SYSTEM OVERRIDE) | per-shell `CLAUDE.md` LAWS / SYSTEM OVERRIDE blocks | source-only — not re-loaded |

Redundancy *would* arise if:
- `~/.claude/CLAUDE.md` ever held LAWS or SEED content (it should be a pointer only).
- The substrate `CLAUDE.md` duplicated identity / mandate content from the per-shell file.
- The per-shell rendered file inlined `shells.connections` (it should be lazy-loaded, not part of the rendered file).
- `skills.content` bodies leaked into the SKILLS block (only `name + description` should render).

Verify each by reading the three flat files and grepping for the canonical phrase from each section. Report any mirror as a trim candidate with char count.

## Step 3 — Stale local files

```bash
ls -la /path/to/dos-arch/shells/cc/ 2>/dev/null
ls -la /path/to/dos-arch/shells/cc/scripts/ 2>/dev/null
ls -la /path/to/dos-arch/shells/cc/_pre_migration_archive/ 2>/dev/null
```

For each file, check: is it (or its parent dir) referenced anywhere in the per-shell `CLAUDE.md` MEMORY ARCHITECTURE table? If yes → used. If no → stale candidate.

Always skip: the rendered `CLAUDE.md` itself, `.shell_managed` (boot marker), `__pycache__/`, `.git/`.

## Step 4 — Report

```
## Memory Audit — CC

### Loaded at boot
| Source | Size | Path |
|---|---|---|
| Universal pointer | {N} B | ~/.claude/CLAUDE.md |
| Substrate project | {N} B | CLAUDE.md |
| Per-shell rendered | {N} B | shells/cc/CLAUDE.md |
Total: ~{N} KB / ~{N} tokens

### Redundancy
{table or "none — single render chain"}

### Not loaded (lazy — by design)
- shells.connections ({N} chars)
- skills.content bodies
- shell_decisions, full_narrative, flag bodies

### Local files
{table of files + status}
```

---

## Notes

- This skill does not modify state. Report only.
- "Redundant" = same data lands in context at boot from two sources. Source-row → render → flat-file is one chain, not redundancy.
- LAWS live in `shell_core/templates/boot.md` (single source of truth, rendered into per-shell `CLAUDE.md`). Any LAWS text outside that file is drift.
- `session_payload` is gone — do not query it; the column was dropped along with its 10 triggers in PR #17. The per-shell file is rendered directly from `shells.current_state` + `shell_identity_entries` + `projects` at boot.