---
name: shared
description: Surface this shell's shared host↔container handoff folder — path + contents.
category: workflow
common: 1
command: --shared
---
# shared

> **Anchors** — `<self>` = your `shell_id:` value, shown in `## BOOT ##` of
> your CLAUDE.md. `<shortname>` is from `## IDENTITY ##`.

Surface this shell's shared workspace. Run on demand with `--shared`.

The shared folder is the host↔container handoff surface — see the `shared`
row in `## DEFINITIONS ##`. *Your* subdir is `~/shared/<NN>-<shortname>/`
inside your container, where `NN` is `<self>` zero-padded to two digits
(e.g. `shell_id=2`, `shortname=sysadmin` → `~/shared/02-sysadmin/`).

## Steps

1. **Compute the path** — `~/shared/{<self>:02d}-<shortname>/`. Both
   anchors come straight out of your boot prompt; no lookup needed.
2. **Inspect** — call the `shared` tool with `{"shell_id": <self>,
   "shortname": "<shortname>"}`. Returns the absolute path plus a
   one-level listing of the four subdirs (count + most-recent entry per
   subdir).
   - If you have no `shared` tool (Claude Code CLI surface), use Bash:
     `ls -la ~/shared/<NN>-<shortname>/` then `ls -la` each subdir.
3. **Surface** to FnB — the path on one line, then per-subdir:
   `redlines (3): latest 2026-05-20 mockup.png` etc. If a subdir is
   empty, say so. If the whole tree is empty, state "shared is empty."

## When to use

- FnB says "in shared" / "check shared" / "drop X in shared" — your
  subdir is the target.
- You want to hand a draft / output back to FnB — write it under
  `review/`.
- Cross-shell handoff — the sibling subdirs are visible too (the whole
  host shared root is mounted, not just yours); reach into
  `~/shared/<other-NN>-<other-shortname>/` directly when collaborating.

## When NOT to use

- For source-of-truth memory (seed, L&S, decisions, flags) — those live
  in the DB over the API (see `## MEMORY PROTOCOL ##`). `shared` is
  for files: screenshots, drafts, exports, snapshots.
- For your working repo — that is `/workspace`, separately mounted.
