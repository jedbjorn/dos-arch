-- 029 — re-seed three skills whose text drifted from the renderer.
--
-- gap-A: surface_flags now passes `?shell_id=<self>` to /flags (server-
--   side scoping, matches the OPEN FLAGS pointer); the manual client-side
--   shell filter is dropped.
-- gap-B: bootstrap_interview's step 2 stops claiming current_state is
--   hard-capped, and points at MEMORY PROTOCOL → CURRENT STATE for
--   ongoing maintenance (now shell-authored). Stale duplicated frontmatter
--   block removed from the body.
-- gap-C: section name `## ACTIVE SESSION` is `## BOOT ##` in the typed
--   catalog. `<self>` and `{archive_id}` references in decision.md,
--   surface_flags.md, and bootstrap_interview.md are repointed. decision
--   step 3 also handles the `archive: —` placeholder gracefully — on API-
--   model shells `shell_memory_archives` is unpopulated, so the narrative
--   PATCH would 404; the decision record itself stays canonical.
--
-- Asset .md files (the fresh-install seed path) were updated in the same
-- PR; seed_from_assets is INSERT-missing-only, so this migration carries
-- the change to already-bootstrapped DBs. Frontmatter (name / description
-- / category / common) is unchanged; only `content` is updated.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

UPDATE skills SET content = '# surface_flags

Surface this shell''s open flags. Run on demand with `--flags`.

Memory is read over the substrate API — no DB file (see MEMORY PROTOCOL
in your system prompt). `<self>` is your `shell_id:`, in `## BOOT ##` of
your CLAUDE.md.

`resolved` is tri-state: `0` = Open, `1` = Resolved, `2` = Tracking.
Unresolved work is **`0` and `2`** — Open flags are active blockers;
Tracking flags are real but not yet effective (future-scheduled). Resolved
(`1`) flags are done and not surfaced.

## Steps

1. **Fetch** — `api_get` on `/flags?shell_id=<self>`. The endpoint
   filters server-side; the response is this shell''s flags only, each
   with its schedule fields.
2. **Filter** — keep only rows where `resolved` is `0` or `2`. Drop the
   rest.
3. **Sort** the kept rows: `resolved` ascending (Open `0` before Tracking
   `2`), then priority High → Medium → Low, then `effective_start`
   ascending (nulls last), then `flag_id`.

## Output — two groups, Open first

**Open Flags** (`resolved == 0`) — active blockers. Columns: ID | Priority | Status | Description | Effective Start | Effective End | Parent

**Tracking** (`resolved == 2`) — real but not yet effective; list below the Open group, same columns.

- Status is `schedule_status` (`scheduled` / `in_progress` / `unscheduled`).
- Effective Start/End come from the flag-schedule view (`parent_flag_id`
  chain + `start_date` override + `estimated_days`).
- If both groups empty: state "No open or tracking flags."
' WHERE name = 'surface_flags';

UPDATE skills SET content = '**API-ONLY** — this skill writes over the substrate API. If a needed
endpoint is unreachable, surface it to the operator and stop — the API is
extended from the repo, never worked around.

---

# decision

- **Trigger:** `--decision`
- **Args:** `[decision] [context]` — interviewed if not provided inline

Record a major decision with context: a decision record (canonical) plus a
line on the active session narrative.

---

## Scope

Applies to **Major decisions** (M priority), including project-architectural
decisions made while working in a code repo. Repo-facing ADR files
(`DECISIONS.md`, `docs/decisions/`) are mirrors for the repo''s audience —
they do **not** substitute for the decision record. The API record is
canonical; repo files link to it, never the reverse.

---

## Steps

`$DOS_API_URL` and `$DOS_API_TOKEN` are in your container environment;
`<self>` is your `shell_id:` and `{archive_id}` is your `archive:` — both
in `## BOOT ##` of your CLAUDE.md.

1. **Resolve args.** If decision or context were not provided inline,
   interview — "What is the decision?", "What is the context — why does this
   matter?" Wait for each answer. Never guess.

2. **Record the decision** — `POST /shells/<self>/decisions`:
   ```bash
   curl -fsS -X POST "$DOS_API_URL/shells/<self>/decisions" \
     -H "Authorization: Bearer $DOS_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d ''{"decision_date": "YYYY-MM-DD", "priority": "M", "decision": "{decision}", "rationale": "{context}"}''
   ```
   Use today''s date. On a non-2xx response: surface the error to the
   operator and stop.

3. **Append to the active session narrative** — `PATCH /shell-memory-archives/{archive_id}`:
   ```bash
   curl -fsS -X PATCH "$DOS_API_URL/shell-memory-archives/{archive_id}" \
     -H "Authorization: Bearer $DOS_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d ''{"narrative_entry": "[HH:MM] DECISION: {decision} — {context}"}''
   ```
   If `{archive_id}` is `—` (no archive row for this session — common on
   API-model shells, where `shell_memory_archives` is unpopulated), skip
   step 3. The decision record from step 2 is canonical; the narrative
   line is a convenience. On any other non-2xx response: surface the
   error to the operator and stop.

4. **Confirm:** "Decision recorded."

---

## Idempotent?

No. Each invocation records a new decision. Fired twice with the same
decision, two identical records are written. Verify before triggering.
' WHERE name = 'decision';

UPDATE skills SET content = '# bootstrap_interview

> Frontmatter (`category`, `common`, `description`) is the source of
> truth — see the YAML block above. Don''t re-state it in the body; it
> drifts.

---

## When to run

You are a shell that was just created via Forge''s `create_shell` skill.
This is your first session — `shells.current_state` is NULL and you have no
`shell_identity_entries` rows yet.

If `current_state` is already populated, you''ve already bootstrapped — do
not re-run.

> **Naming note:** this skill no longer runs an interview — Forge does the
> whole interview at creation. It now only covers the two things a shell
> must do for *itself*. The name is kept for reference stability.

---

## What is already done

Forge''s `create_shell` set your `system_prompt`, `display_name`,
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
runs in a container with no `sqlite3` (see MEMORY PROTOCOL in your system
prompt). `$DOS_API_URL` and `$DOS_API_TOKEN` are in your container
environment; `<self>` is your `shell_id:`, shown in `## BOOT ##` of your
CLAUDE.md.

## 2. Set current_state

A tight rolling status — aim ~280 chars (soft cap, as of migration 020).
Not a log. Just: who you are now, and the first task. After this first
write, `current_state` is yours to maintain as work moves (see MEMORY
PROTOCOL → CURRENT STATE).

```bash
curl -fsS -X PATCH "$DOS_API_URL/shells/<self>" \
  -H "Authorization: Bearer $DOS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d ''{"current_state": "Bootstrapped. Partner: <username>. Next: <first task agreed with operator>."}''
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
  -d ''{
        "kind": "seed",
        "body": "Bootstrapped today. Partner: <username>. Mandate: <mandate>. What I notice about the work ahead: <one real observation>."
      }''
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

## 5. Record host hardware

The substrate tracks the machines it runs on in `user_hardware`, and any
local LLM models in `models`. Record this machine on first boot so the
environment is live in the DB from the start:

```
make collect-hardware
```

If Ollama is installed on this machine, also sync the model set:

```
make sync-models
```

Both are safe to re-run whenever hardware or the installed model set
changes. See `docs/model-tiers.md` for hardware/model guidance, and the
install README for the full picture.

---

## 6. Confirm to operator

> "Bootstrapped. current_state set. First seed entry planted. Ready for:
> `<first task>`."

Then move to that first task. Next session boots with everything loaded
into your CLAUDE.md by `run.py`.

---

## What this skill does NOT do

- It does not interview for identity, domain, or environment — Forge''s
  `create_shell` did all of that.
- It does not set `system_prompt`, `display_name`, `shortname`, `partner`,
  `role`, `mandate`, or `connections`.
- It does not assign groups or projects — that is a separate step.
- It does not create users.
' WHERE name = 'bootstrap_interview';

