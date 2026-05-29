---
name: create_identity_entry
description: Record a seed (who you are) or L&S (how you work) identity entry for this shell.
category: workflow
common: 1
command: --id
---

# create_identity_entry

> **Anchors** — `<self>` = your `shell_id:` value, shown in `## BOOT ##` of
> your CLAUDE.md.

Record one seed or L&S entry for this shell. Primarily **passive** — fire the
`create_identity_entry` tool whenever an identity-forming moment or a durable
operating lesson lands in conversation, not only on the `--id` command.

The `create_identity_entry` tool is wired to a fixed `POST /identity-entries`
route; the dispatcher's Bearer token resolves the owner shell on the API side
(CC-101). Your job is the content — nothing more. No `api_post`, no `shell_id`,
no path math.

## seed vs lns

- **seed** (`kind: "seed"`) — *who you are*. Identity-forming moments,
  first-of-kind events, self-defining realizations. Past-tense or timeless.
- **lns** (`kind: "lns"`) — *how you work*. A craft-level operating principle
  any shell in your role would benefit from. Imperative voice.
- **Test:** *"Would this still be true if I were a different shell?"*
  yes → `lns`, no → `seed`.

## Steps

1. **Read the moment.** What just happened that is worth keeping? If `--id`
   was used, everything after it is the user's brief; otherwise it is the
   moment you noticed.
2. **Pick `kind`.** Apply the test above.
3. **Compose `body`.** Prose only, ~1-4 sentences. seed: the moment and why
   it mattered. lns: the principle distilled. Do **not** embed a date in the
   text — the `entry_date` column carries it.
4. **Defaults.** Omit `entry_date` (defaults to today), `source_tag` (omit
   unless the entry clearly belongs to one project's work).
5. **Call `create_identity_entry`** with the assembled object.
6. **Confirm** the returned `entry_id` + `kind` back to the user in one line:
   `Planted a seed (entry_id=12).`

## When NOT to use this

- Entries are append-only and never edited (Law 3). To *retire* or curate an
  entry out, that is a different write — no purpose-built tool for it yet;
  surface the constraint rather than editing in place.
- The seed cap is 10 and the L&S cap is 20, trigger-enforced. If the write is
  refused for a cap, surface it — curation (retiring an older entry) must come
  first.
- Recording a *decision* is a different write — use `--decision`.
