---
name: bootstrap_interview
description: Run once on a fresh shell's first session. Identity is already set by Forge's create_shell interview — this skill is the new shell's own first act: plant its first seed entry and set a starter current_state. Not an interview.
category: workflow
common: 1
---
# bootstrap_interview

- **category:** workflow
- **common:** 0
- **description:** Run once, on the first session of a fresh shell. Identity, system_prompt, connections, and skills are already set by Forge's `create_shell` interview — this skill is the new shell's own first act: plant its first seed entry and set a starter `current_state`. Not an interview.

---

## When to run

You are a shell that was just created via Forge's `create_shell` skill.
This is your first session — `shells.current_state` is NULL and you have no
`shell_identity_entries` rows yet.

If `current_state` is already populated, you've already bootstrapped — do
not re-run.

> **Naming note:** this skill no longer runs an interview — Forge does the
> whole interview at creation. It now only covers the two things a shell
> must do for *itself*. The name is kept for reference stability.

---

## What is already done

Forge's `create_shell` set your `system_prompt`, `display_name`,
`shortname`, `partner`, `role`, `mandate`, `connections`, and skill
attachments. Read your rendered CLAUDE.md — that is your identity. You do
not re-gather any of it.

Group and project assignment are handled separately (admin portal). If you
have no `project_shells` rows yet, that is expected — wait for assignment
or let the operator assign them directly.

---

## 1. Confirm the first task

Ask the operator: what is the first thing this shell should work on? You
need it for `current_state`. Keep it short.

---

Memory is written over the **substrate API** — never a DB file; this shell
runs in a container with no `sqlite3` (see MEMORY ARCHITECTURE in your
system prompt). `$DOS_API_URL` and `$DOS_API_TOKEN` are in your container
environment; `<self>` is your shell_id, shown in `## ACTIVE SESSION` of
your CLAUDE.md.

## 2. Set current_state

A tight rolling status — **280 characters max**, enforced server-side. Not
a log. Just: who you are now, and the first task.

```bash
curl -fsS -X PATCH "$DOS_API_URL/shells/<self>" \
  -H "Authorization: Bearer $DOS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"current_state": "Bootstrapped. Partner: <username>. Next: <first task agreed with operator>."}'
```

---

## 3. Plant your first seed entry

This is yours to write — per the Laws, a shell curates its own seed; no
other shell, not even Forge, authors it. One `seed` identity-entry — prose
body, dated today. It should read like the start of a story, not a status
line.

```bash
curl -fsS -X POST "$DOS_API_URL/shells/<self>/identity-entries" \
  -H "Authorization: Bearer $DOS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "kind": "seed",
        "body": "Bootstrapped today. Partner: <username>. Mandate: <mandate>. What I notice about the work ahead: <one real observation>."
      }'
```

`entry_date` defaults to today server-side — pass it only to backdate.
Counts toward the 10-seed cap (enforced server-side); you have 9 slots
left.

---

## 4. Discover the catalogue

The substrate keeps a live index of its own components (APIs, routers,
deps, libs, services, paths, env vars) in the `dr_*` family, exposed via
`v_dr_catalogue` and `v_shell_catalogue`. When you need to find something,
query the catalogue first, before grepping the codebase. See the
`catalogue_sync` and `surface_catalogue` skills.

---

## 5. Confirm to operator

> "Bootstrapped. current_state set. First seed entry planted. Ready for:
> `<first task>`."

Then move to that first task. Next session boots with everything loaded
into your CLAUDE.md by `run.py`.

---

## What this skill does NOT do

- It does not interview for identity, domain, or environment — Forge's
  `create_shell` did all of that.
- It does not set `system_prompt`, `display_name`, `shortname`, `partner`,
  `role`, `mandate`, or `connections`.
- It does not assign groups or projects — that is a separate step.
- It does not create users.
