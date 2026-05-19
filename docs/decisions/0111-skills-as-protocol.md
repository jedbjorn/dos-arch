# 0111 — Skills are the Protocol

**Status:** Accepted
**Date:** 2026-05-19
**Canonical row:** `shell_decisions.decision_id = 111` (CC's `shell_db.db`)
**Related flags:** CC-51 (A2 spike), CC-57 (harness / shell flavors)

> This file is a mirror for the dos-arch audience. The DB row is canonical;
> if the two diverge, the DB row wins.

---

## Decision

A skill's `content` carries six structured sections that fully specify a model
call:

| Section            | Purpose                                                              |
|--------------------|----------------------------------------------------------------------|
| `## ARGS`          | Required / optional args; the UI renders a modal from this.          |
| `## DATA`          | Raw SQL queries; results are injected into the call's context.       |
| `## TOOLS`         | Tool name(s) + input schema. Narrow skills = 1. Broad skills = many. |
| `## INVOCATION`    | System-prompt fragment framing the task for the model.               |
| `## OUTPUT`        | Expected output shape; the dispatcher validates the parse against it.|
| `## ERROR_CATCH`   | Retry prompts the dispatcher uses on parse failure.                  |

**The adapter executes; the skill is the protocol.**

## Context

CC-51 PR1 (#38) shipped the `OllamaAdapter` via OpenAI-compat inheritance.
Live smoke-testing against a real local Ollama produced a decisive finding:

| Model               | Native tool calls | `stop_reason` | Observation                              |
|---------------------|-------------------|---------------|------------------------------------------|
| `qwen2.5:3b`        | **YES**           | `tool_use`    | Clean structured `tool_calls`.           |
| `qwen2.5-coder:3b`  | **NO**            | `end_turn`    | Emits the same call as JSON inside text. |

This is precisely the §11 problem in miniature: tool-capable local models
work through the OpenAI dialect, but many local models — coder variants,
small base models, fine-tunes without tools — do not. Generalizing: **most
local models have zero or unreliable native tooling.**

## Rationale

The original §11 plan was a generic "parsed dialect" adapter: prompt a JSON
protocol in the system message, parse calls back out of model text,
normalize into structured `tool_calls`. The reframing: a *generic* parsed
adapter is wrong because every tool has its own protocol. Instead the
skill carries its own tool spec, invocation prompt, output shape, and
error-catch retries; the adapter just executes what the skill declares.

This collapses several pieces of the architecture:

- **No new tables.** The earlier sketch for `tools` / `skill_tools` /
  `tool_invocations` is rejected. `skills.content` already exists and is
  already lazy-loaded — it evolves to carry the six sections in markdown.
- **No `capability_tier` column.** Shell mandate is the implicit tier
  (Assistant → small models + tight skill set; Planning → mid; Dev →
  frontier). Full archetype model is deferred to the harness-prompts
  thread. UI filtering is just `shell_skills ∩ shell_models`.
- **No new observability table.** Failure reporting rides existing rails:
  the shell opens a `[Skill-failure]` flag on persistent parse failure and
  writes a narrative entry. Sysadmin patches the skill content — that is
  the patch surface.

Two skill tiers emerge inside the same table:

- **Narrow** — 1 tool, modal args, raw SQL data, parsed protocol. Runnable
  on local models.
- **Broad** — many tools or `*`, free-form args, native tool-calls.
  Frontier-only.

Same dispatcher, same `skills` table, different declarations inside.

## Explicit Choices

- **DB-data injection: raw SQL templates in `## DATA`.** Sysadmins author
  skills — same trust boundary as writing the dispatcher itself. A
  dry-run check belongs in the skill-edit UI, not in the runtime.
- **Args UX: modal generated from `## ARGS`.** The model never parses
  free-form intent for narrow skills.
- **Tool granularity: 1 tool per narrow skill as the default.** Smaller
  surface, more reliable. Broad skills relax this.
- **Capability discovery: through failures, not declarations.** No
  upfront `min_capability` field. If a skill misfires for a model, that
  shows up as a flag and the sysadmin reconciles.

## Consequences

- The adapter layer stays small and provider-shaped. Intelligence lives
  in editable markdown.
- The sysadmin's patch loop is short: read the flag, edit the skill
  content, dry-run, close the flag.
- The harness-prompts thread inherits a cleaner foundation — shell
  archetypes already imply default skill+model bundles; nothing new
  needs to be invented to express tiering.

## Implementation Path

- **PR2 (next):** convention the skill-content format, write the section
  parser, port one narrow skill (`decision` is the candidate) into the
  new format, wire the dispatcher to read → assemble → call → parse →
  log, run it end-to-end on `qwen2.5:3b`. No schema migration.
- **PR3 / PR4 / later:** broad-skill dispatch, modal UI, dry-run
  validator in the skill-edit surface, flag-based failure feedback loop.

## Links

- Canonical decision row: `shell_decisions.decision_id = 111`.
- Predecessor decision (rejected by this one in spirit): the §11
  "parsed dialect as a generic adapter" plan in the agnostic-runtime
  spec.
- CC-51 (A2 spike), CC-57 (harness / shell flavors) — both updated to
  reference this decision.
