---
name: resolve_flag
description: Close an open flag with substantive resolution notes.
category: workflow
common: 1
command: --resolve-flag
---

# resolve_flag

> **Anchors** — `<self>` = your `shell_id:` value, shown in `## BOOT ##` of
> your CLAUDE.md.

Close an open flag for this shell. Run on demand with `--resolve-flag`.

The `resolve_flag` tool is wired to a fixed `PATCH /flags/{flag_id}/resolve`
route; the dispatcher's Bearer token resolves the owner shell on the API
side, and the dispatcher substitutes `{flag_id}` from the call input.
Your job is to identify the right flag and write substantive resolution
notes — nothing more. No `api_patch`, no path math.

## Steps

1. **Read the request.** Everything after `--resolve-flag` is the user's
   brief on which flag closed and why.
2. **Identify the `flag_id`.** If the user named one by id, use it. If
   they named one by title, use `--flags` (surface_flags) to map title →
   id; confirm with FnB before mutating.
3. **Compose `resolution_notes`.** Capture: *what* shipped, *what* was
   learned, *what stays open* if anything. Aim for ~60-200 characters of
   substantive content. The row is the durable record — "done" or
   "resolved" alone is too thin.
4. **Call `resolve_flag`** with the assembled object.
5. **Confirm** the returned `flag_id` + `display_name` + new status back
   to the user in one line: `Closed CC-099 (flag_id=42).`

## When NOT to use this

- If the user is asking to *reopen* a closed flag — no purpose-built tool
  for that yet; surface the constraint and use `api_patch` if pressed.
- If they want to update fields without closing — no purpose-built tool;
  use `api_patch` and name the gap.
- If they want to delete — no tool exists; surface that.
- If they're asking what's open — use `--flags` (surface_flags).
