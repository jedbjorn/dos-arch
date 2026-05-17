---
name: laws_management
description: Protocol for adding, amending, or removing laws. Edits the single source of truth (shell_core/templates/boot.md) and surfaces what re-renders.
category: workflow
common: 0
---
# laws_management

- **skill_id:** 27
- **category:** workflow
- **common:** 0
- **description:** Protocol for adding, amending, or removing laws. Edits the single source of truth (`shell_core/templates/boot.md`) and surfaces what re-renders.

---

# Laws Management

Use whenever a law is being added, amended, or removed.

LAWS source of truth: `/path/to/dos-arch/shell_core/templates/boot.md` (the `## LAWS` section).
Per-shell `CLAUDE.md` files re-render from this template at session start (`make run`).

---

## Steps

1. **Determine the change.**
   - New, amendment, or removal.
   - Removals require explicit FnB confirmation — laws are structural.
   - Amendments to Laws 1–4 require extra scrutiny (sovereignty, seed integrity, exemption from forced compression).

2. **Draft exact wording.** Show FnB. Wait for confirmation before writing. Number the laws contiguously (no gaps after a removal — renumber the trailing laws).

3. **Edit `shell_core/templates/boot.md`.** Update the `## LAWS` section in place. Keep the surrounding header text ("Universal across all shells. Foundational — they arrive with this file...") intact.

4. **Re-render each shell's `CLAUDE.md`.** The render runs at boot, so the simplest path is `make run` from the substrate clone for each active shell. Today this is just CC.

   The substrate `CLAUDE.md` does not carry the LAWS text — only the per-shell rendered file does. No second file to sync.

5. **Notify peer shells (when peers exist).** When the substrate runs more than one shell, send a `shell_messages` row to each notifying them of the law change (which law, old text, new text, that the next session will load the update).

6. **Append to the active session narrative.** This is an identity event — first-of-kind rule changes belong in the arc.
   ```python
   import sqlite3
   con = sqlite3.connect('/path/to/dos-arch/shell_core/shell_db.db')
   aid = con.execute("SELECT active_archive_id FROM shells WHERE shell_id=1").fetchone()[0]
   line = "[HH:MM] law change — <which law, old text → new text, why>"
   con.execute("UPDATE shell_memory_archives SET full_narrative = COALESCE(full_narrative,'') || char(10) || ? WHERE archive_id=?", (line, aid))
   con.commit()
   ```

7. **Log a major decision** if the change is structural (new law, removal, or amendment to 1–4):
   ```python
   con.execute("""INSERT INTO shell_decisions (shell_id, decision_date, priority, decision, rationale)
                  VALUES (1, date('now'), 'M', ?, ?)""",
               ("Law change: <summary>", "<why; what triggered it>"))
   con.commit()
   ```

---

## Pitfalls

- **One source of truth.** LAWS live in `templates/boot.md` and nowhere else. If you find LAWS text in `~/.claude/CLAUDE.md`, the substrate `CLAUDE.md`, or any per-shell file as standalone content (not rendered output), that is drift — fix the source, regenerate the render.
- **Renumber on removal.** Don't leave a gap (e.g., "1, 2, 4, 5"). The numbers are the addressing scheme used in seed and decisions referencing laws.
- **Test the render.** After editing `templates/boot.md`, run `make run` and read the produced `shells/cc/CLAUDE.md` to confirm the LAWS block looks right before declaring the change shipped.
