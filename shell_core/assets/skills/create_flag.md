---
name: create_flag
description: Open a new flag (work tracker / blocker) for this shell.
category: workflow
common: 1
command: --new-flag
---

# create_flag

> **Anchors** — `<self>` = your `shell_id:` value, shown in `## BOOT ##` of
> your CLAUDE.md.

Open a new flag for this shell. Run on demand with `--new-flag`.

The `create_flag` tool is wired to a fixed `POST /flags` route; the
dispatcher's Bearer token resolves the owner shell on the API side
(migration 031). Your job is to gather the content fields — nothing more.
No `api_post`, no `shell_id`, no `flag_id` math.

## Steps

1. **Read the request.** Everything after `--new-flag` is the user's brief.
   Free-form. Extract a short title + a longer description.
2. **Pick a `display_name`.** Short, distinctive, scoped (e.g.
   `CC-099 docs sweep` or `dispatcher reaper smoke-test`). The shell-prefix
   convention is optional — match what siblings on this shell already use.
3. **Compose `description`.** Capture: *what* the flag tracks, *why* it
   matters, and (if known) *what unblocks when it closes*. The flag is the
   work-of-record — be specific enough that future-you can act on it
   without re-reading this chat.
4. **Defaults.** Omit `priority` (defaults `Medium`), `start_date` (open
   now), `parent_flag_id` (none), `estimated_days` (unknown) unless the
   user named them. Don't invent values.
5. **Call `create_flag`** with the assembled object.
6. **Confirm** the returned `flag_id` + `display_name` back to the user
   in one line: `Opened CC-099 (flag_id=42).`

## When NOT to use this

- If the user is asking to *resolve* or *update* an existing flag — that
  is a different write (no tool for it yet; surface that constraint
  rather than opening a duplicate).
- If they're asking what's open — use `--flags` (surface_flags).
