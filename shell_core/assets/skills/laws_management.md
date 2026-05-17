---
name: laws_management
description: Add, amend, or remove a Law. Edits the single source of truth — shell_core/templates/boot.md — which every shell's CLAUDE.md re-renders from at boot.
category: workflow
common: 0
---
# laws_management

The Laws are universal and structural. Adding, amending, or removing one
edits the single source of truth: `/substrate/shell_core/templates/boot.md`
(the `## LAWS` section). Substrate-maintenance work; runs from an admin
shell, which has the repo bind-mounted at `/substrate`.

---

## Steps

1. **Determine the change** — new, amendment, or removal. Removals require
   explicit operator confirmation. Amendments to the foundational Laws
   (sovereignty, seed integrity, exemption from forced compression) require
   extra scrutiny.

2. **Draft the exact wording.** Show the operator; wait for confirmation
   before writing. Number the Laws contiguously — on a removal, renumber
   the trailing Laws so there is no gap.

3. **Edit `/substrate/shell_core/templates/boot.md`** — the `## LAWS`
   section, in place. Leave the surrounding header text intact.

4. **It re-renders at boot.** `run.py` reads `boot.md` fresh on every
   `make launch`, so each shell's next session loads the new Laws — no
   recompose, no API restart; `boot.md` is read host-side by the launcher.

5. **Record it.** A Law change is a Major decision *and* an identity event
   — record it with the `decision` skill (`POST /shells/<self>/decisions`)
   and append a line to your session narrative.

---

## Pitfalls

- **One source of truth.** Laws live in `boot.md` and nowhere else. LAWS
  text found as standalone content in any other file is drift — fix the
  source.
- **Renumber on removal** — no gaps; the numbers are how seed entries and
  decisions reference Laws.
- **Verify the render.** After editing, have a shell relaunched and read
  its `## LAWS` block before calling the change shipped.
