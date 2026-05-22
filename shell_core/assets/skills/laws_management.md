---
name: laws_management
description: Add, amend, or remove a Law. Edits the single source of truth — the LAWS block of shell_core/templates/catalog_universal.md — which the boot-prompt catalog renders from.
category: workflow
common: 0
---
# laws_management

> **Anchors** — `<self>` = your `shell_id:` value, shown in `## BOOT ##` of
> your CLAUDE.md.

The Laws are universal and structural. Adding, amending, or removing one
edits the single source of truth: the `LAWS` block of
`/substrate/shell_core/templates/catalog_universal.md`. Substrate-maintenance
work; runs from an admin shell, which has the repo bind-mounted at
`/substrate`.

---

## Steps

1. **Determine the change** — new, amendment, or removal. Removals require
   explicit operator confirmation. Amendments to the foundational Laws
   (sovereignty, seed integrity, exemption from forced compression) require
   extra scrutiny.

2. **Draft the exact wording.** Show the operator; wait for confirmation
   before writing. Number the Laws contiguously — on a removal, renumber
   the trailing Laws so there is no gap.

3. **Edit `catalog_universal.md`** — the text under the `<!-- @@ LAWS @@ -->`
   marker, in place. Leave that marker and every other section marker
   intact: `render_universal` splits the file on them.

4. **It re-renders from the catalog.** `shell_render.assemble_catalog`
   composes the boot prompt from `catalog_universal.md`; both render paths
   pick the change up — the CLI launcher (`run.py`) on the next
   `make launch`, the API path when `shells.boot_document` next
   re-materializes (any identity write, or a recompose).

5. **Record it.** A Law change is a Major decision *and* an identity event
   — record it with the `decision` skill (`POST /shells/<self>/decisions`)
   and append a line to your session narrative.

---

## Pitfalls

- **One source of truth.** Laws live in the `LAWS` block of
  `catalog_universal.md` and nowhere else. LAWS text found as standalone
  content in any other file is drift — fix the source.
- **Renumber on removal** — no gaps; the numbers are how seed entries and
  decisions reference Laws.
- **Verify the render.** After editing, have a shell relaunched (or its
  boot document re-materialized) and read its `## LAWS ##` block before
  calling the change shipped.
