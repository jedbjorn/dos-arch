---
name: file-ops
description: Read, edit, search, and author files in the working directory.
category: workflow
common: 0
trigger_keywords: read file, edit file, write file, search files, find file
trigger_use_when: reading, editing, or searching files in the working directory
---
# file-ops

Read, edit, search, and author files in the working directory. The file
tools render in your TOOLS section when this skill is granted.

## When to reach for it
Reading, editing, writing, or searching files. The tools: file_read,
file_write, file_edit, file_append, file_list, file_search, file_find,
file_delete, file_move.

## Workflow

**Find the thing**
1. file_search (contents) or file_find (names) — narrow to candidates.
2. file_read with a line range — confirm before acting.

**Edit the thing**
1. file_read first — see the current content.
2. file_edit with a unique old_str — a non-unique match is rejected, not
   guessed at; add surrounding context until it is unique.
3. file_read the edited region — verify.

**Create the thing**
1. file_find to confirm it does not already exist.
2. file_write — it fails if the path is already there; use file_edit for an
   existing file.

## Never
- file_edit blind — always file_read first.
- file_delete without naming, in the same reply, what is being deleted and
  why. file_delete refuses a directory; it is a single-file tool.
- file_write to a path you have not confirmed is absent.

## Stop
- After a destructive op (delete, move) — announce it; do not chain.
- After an edit and its verification — announce the result; do not chain.
