---
title: DOS-Arch — Cold Agents Spec
tags: [dos-arch, spec, agents, architecture]
date: 2026-05-26
project: dos-arch
purpose: Cold agent definition + run contract
---

## Status

> [!class1]
> Draft — living specification. 2026-05-26.

Peer to `docs/specs/agnostic-runtime.md` and `docs/specs/memory-recall.md`.
The agnostic-runtime spec introduces cold agents at the layer level
(§3.2) and leaves their storage open (§4.6). The memory-recall spec
relies on three **named** cold agents (`summarizer-agent`,
`decision-expander-agent`, `recall-agent`) without specifying how they
are defined or invoked. This spec is the formal definition those two
peer specs reference: what a cold agent **is** as a stored artifact,
how it runs, how it is authorized, and how its results flow back.

This spec **supersedes** `agnostic-runtime.md` §4.6 ("Cold agents are
not stored"). Cold agents become **named, stored definitions**; an
individual **run** of an agent remains ephemeral and identity-less. The
distinction matters — definition and execution are different things,
and conflating them was the load-bearing weakness of §4.6 once
memory-recall started naming agents.

It does **not** restate runtime, provider, dispatcher, model-registry,
or tool-registry concerns. Those are owned by `agnostic-runtime.md` and
referenced here.

## 1. Purpose and scope

### Purpose

Define the **cold-agent contract** so a dos-arch substrate can host a
catalog of named, pinned, scoped, testable execution capabilities —
each one a known-good `(task, model, tools)` triple that a shell or
a scheduled trigger can invoke and receive a structured trace from.

The framing is **calibrated capability**, not generic delegation. An
agent is not "anything with an LLM"; it is one specific task, verified
to work with one specific model under one specific tool grant. When a
local 7B model handles `file_read + file_search` reliably for a defined
task, that combination is an agent. When a frontier model is required
for nuanced multi-file analysis, that is a different agent. The pin is
load-bearing.

This unlocks two things the substrate has needed and lacked:

1. **Local-first execution.** Pinning makes small local and
   ollama-cloud models viable for bounded jobs. The substrate stops
   defaulting to "use the strongest model for everything" because the
   tool/model fit is encoded per agent, not per call site.
2. **Regression-testable agents.** A named (task, model, tools) triple
   has a fixed I/O contract. A test fixture can exercise it; a model
   change surfaces the break before deploy.

Underneath both unlocks: calibration is how you work the material. A
bounded task plus a specific tool grant plus a specific model lets you
find out what that combination actually *wants to be*. Generic
delegation flattens the material into "throw it at the strongest
model" and loses the answer; pinning preserves the question. The
agent primitive is built around discovering those answers, one
calibration at a time.

### Scope

In scope: the cold-agent asset format, the `agents` and `agent_runs`
tables, the execution contract (depth, turn count, return shape), the
auth model, the three trigger surfaces (manual / scheduled / shell),
failure handling, and the alpha→beta→release runtime evolution path.

Out of scope, owned by `agnostic-runtime.md`: the dispatcher loop, the
`ProviderAdapter` seam, the `models` registry, the `tools` registry,
`shell_skills` and the `cold_portable` flag, the boot-document
assembly, the chat surface.

Out of scope, owned by `memory-recall.md`: the specific behavior of
`summarizer-agent`, `decision-expander-agent`, and `recall-agent`.
This spec defines what they **are structurally**; the memory spec
defines what they **do**.

### Lineage

Five things shape this spec.

| Source | Contributes |
|---|---|
| agnostic-runtime §3.2 | Cold agent = ephemeral, identity-less, single-task. Kept verbatim. |
| agnostic-runtime §4.6 | "Not stored." **Superseded** — definitions are stored; runs are ephemeral. |
| memory-recall §3.2 | Three named agents, scoped tool grants as data, two trigger paths (dispatcher / shell). Implicitly already required stored agents. |
| External coding-agent catalog (OpenCode, Claude Code subagents, picocode) | Asset shape (markdown frontmatter + body), per-agent tool-list field, description-as-trigger-hint. Mined, not adopted wholesale. |
| The discussion that produced this spec | Pin-to-model as load-bearing, depth=1 cap, one-shot runtime, trace-return as primary I/O. |

### Where this sits

dos-arch decomposes AI implementation into four primitives — **model**,
**harness**, **agent**, **shell** (see README). This spec defines the
agent primitive: calibrated execution capability — a directive, a tool
grant, and an output shape, pinned to a model verified to handle them.
Identity, memory, review, and composition live in the **shell**
primitive by design (§10). The substrate has no separate workflow
primitive; workflow is what emerges when shells compose agents and
other shells.

## 2. Terminology

| Term | Meaning |
|---|---|
| **Cold agent** (or **agent**) | A named, stored definition: `(task brief, pinned model, scoped tools, trigger spec)`. Identity-less. Per agnostic-runtime §3.2 — no memory, no continuity across runs. |
| **Run** | One execution of an agent. Ephemeral. Produces one `agent_runs` row. The run is what is identity-less; the *definition* it executes is named. |
| **Pin** | An agent's required `model_id` from the `models` registry. Not a default, not a fallback — the model **is** part of the agent's contract. |
| **Scoped grant** | The exact subset of the `tools` registry this agent may call. Must be `cold_portable = 1` (per agnostic-runtime §4.4) and must be a subset of the spawning shell's grant (for shell-spawned triggers). |
| **Trace** | The ordered list of tool calls and tool results produced during a run, plus the model's final text. The substrate of any downstream analysis. |
| **Parent shell** | For shell-spawned and manual runs: the shell whose authority backs the run. For scheduled runs: NULL — the scheduler is the principal. |

> [!class2]
> **One run, one agent.** A run executes exactly one agent definition. An agent cannot spawn another agent — see §6.

## 3. Execution contract

### 3.1 One-shot, depth=1, max-turns configurable

A run is **one model call** by default. The model receives the task
brief and the scoped tools, emits its tool-call requests, the runtime
executes those tools, results are appended to the trace, and the run
ends — the caller (shell or scheduler) interprets the trace.

A `max_turns: N` field on the agent definition (default `1`) lifts
this. Setting `max_turns: 3` lets the runtime feed tool results back
into the model for up to three rounds before terminating. The default
is one because:

- It is the simplest contract a model can fail to follow.
- It removes the "infinite tool loop" failure mode by construction.
- Small models are worse at multi-turn tool reasoning anyway — one-shot
  is the format their actual capability fits.

`max_turns > 1` is permitted but is the agent author's explicit
opt-in. It is also the alpha→beta hinge — see §9.

### 3.2 Depth = 1

An agent **cannot spawn another agent.** This is enforced at the
spec level: no agent's scoped tool grant may include the
`agent.run` tool (or any tool whose handler invokes the agent
runtime). The dispatcher's tool-grant validator rejects on load.

Simple orchestration — calling agent A, reviewing the trace, then
calling agent B — lives in the **shell**, where review already
exists. Orchestration that needs review and orchestration that needs
authority belong in the same layer. The substrate does not build a
second one. Equivalently: composition of agents into workflows is the
shell primitive's territory; agents stay primitive units.

### 3.3 Return shape

A run's output is structured. All three of the following are returned
together:

```json
{
  "status": "ok | error | timeout",
  "text": "the model's final text response",
  "trace": [
    {"call": {"tool": "file_read", "args": {}}, "result": {}, "is_error": false}
  ],
  "meta": {"tokens_in": 0, "tokens_out": 0, "duration_ms": 0, "model": "qwen2.5-coder:7b"}
}
```

Both `text` and `trace` are always populated when the run completed
the model call — neither is conditional on the other. The caller
chooses what to read. The runtime never silently drops `trace` to save
storage; truncation, if any, applies per-tool-result (see §7) and is
recorded as `truncated: true` on the offending entry.

This decision (return both) is deliberate. The executor model may be
small; the reviewer (the shell, or a larger model the shell calls) may
be large. **Reviewing what the executor did is the work of the larger
model**, and reviewing requires the trace. Returning only the text
would force the substrate into a trust-the-executor posture it cannot
afford.

## 4. Storage

### 4.1 Asset format

Cold agents are authored as markdown files in
`shell_core/assets/agents/<name>.md`, following the same
frontmatter-into-columns + body-as-content pattern as `assets/tools/`
and `assets/skills/`. A `_seed.toml` in the directory tells
`seed_from_assets` how to populate the `agents` table.

```markdown
---
name: summarizer-agent
description: Summarize a closed chat session into sessions.summary.
model: qwen2.5-coder:7b
max_turns: 1
trigger_kind: dispatcher
schedule: null
tools: [file_read, db_query_sessions, db_write_session_summary]
timeout_seconds: 60
max_tool_calls: 16
---
You are a summarization agent. Read the supplied chat_messages span
and write a one-paragraph summary to sessions.summary for the
session_id passed in your task input. Do not write to any other
table. Do not exceed 600 characters.
```

The body is the **system prompt** delivered to the pinned model.
Authors write it as a real system prompt — terse, imperative, scoped.

### 4.2 The `agents` table

| Column | Type | Notes |
|---|---|---|
| `agent_id` | INTEGER PK | |
| `name` | TEXT UNIQUE | Matches the asset filename and frontmatter. |
| `description` | TEXT | One line. Used by triggers — see §6.3. |
| `model_id` | INTEGER FK → models | The pin. Required, never null. |
| `system_prompt` | TEXT | Body of the asset. |
| `max_turns` | INTEGER DEFAULT 1 | §3.1. |
| `trigger_kind` | TEXT | `dispatcher` / `shell` / `manual` / `scheduled`. §6. |
| `schedule` | TEXT NULL | Cron expression; required iff `trigger_kind = scheduled`. |
| `timeout_seconds` | INTEGER DEFAULT 60 | Per-run hard ceiling. §7. |
| `max_tool_calls` | INTEGER DEFAULT 16 | Cap across all turns. §7. |
| `status` | TEXT DEFAULT 'active' | `active` / `deprecated`. |
| `is_deleted` | INTEGER DEFAULT 0 | |
| `created_at` | DATETIME | |

The agent's scoped tool grant is a join — `agent_tools(agent_id,
tool_id)` — populated from the frontmatter `tools:` list at seed
time. A tool that is not `cold_portable = 1` in the `tools` registry
is rejected at seed: cold agents may not be granted shell-only tools.

### 4.3 The `agent_runs` table

Every run produces a row. The row is **append-only** — runs are
historical facts, never mutated after the run ends.

| Column | Type | Notes |
|---|---|---|
| `run_id` | TEXT PK | UUID, minted at run start. |
| `agent_id` | INTEGER FK → agents | |
| `parent_shell_id` | INTEGER FK → shells NULL | Set for `shell` and `manual` triggers; NULL for `scheduled` and `dispatcher`. |
| `trigger_kind` | TEXT | Mirrors `agents.trigger_kind` at run time — set on the row so deprecating the agent or changing its trigger does not falsify history. |
| `started_at` / `finished_at` | DATETIME UTC | |
| `status` | TEXT | `ok` / `error` / `timeout`. See §7. |
| `text` | TEXT | Final model text. |
| `trace_json` | TEXT | The §3.3 trace, serialized. |
| `error_code` / `error_message` | TEXT NULL | Set for non-`ok` runs. |
| `meta_json` | TEXT | Tokens, duration, model name at time of run. |

`agent_runs` is the substrate's **single source of truth for what
happened**. The reviewer model (shell or larger model called by the
shell) reads `trace_json`. Operators read it for audit. Tests assert
against it.

## 5. Auth and identity

A run needs the right to call its scoped tools. The substrate has two
shapes of principal today: shells (Bearer-token, audit-trail in the
shell's name) and the dispatcher (system principal). Agents are
neither.

**An agent run is granted an ephemeral, run-scoped token, minted at
run start, expiring at run end.** The token's claims encode:

- The `agent_id` (what is acting)
- The `run_id` (which execution)
- The `parent_shell_id` if any (who delegated)
- The scoped tool grant (what may be called)

Every audited tool call from the run records all three of `agent_id`,
`run_id`, `parent_shell_id` — so the audit story remains "agents are
spawned by shells, accountable to shells" even when the agent's own
authority is what the substrate checked at call time.

For `scheduled` runs, `parent_shell_id` is NULL and the scheduler is
the principal. The audit story degrades to "scheduled agent X fired
on time Y" — adequate, because scheduled agents are operator-owned
infrastructure, not collaborator-owned acts.

The broker that already issues service tokens for dos-arch
(`dos-broker`) extends to issue run-scoped tokens. The agent runtime
requests one at run start; it returns it (or it expires) at run end.
Revocation is per-token, never cascading to the parent shell.

## 6. Triggers

An agent has exactly one `trigger_kind`. The four kinds are not
interchangeable — each implies a different invocation surface and a
different audit story.

### 6.1 `dispatcher`

Invoked by the runtime itself. The dispatcher knows the right moment —
a session closed, a `‹decision›` marker landed (per memory-recall
§3.2). The shell does not know the run happened. `parent_shell_id`
is NULL.

The set of dispatcher-triggered hooks is **hardcoded in the
dispatcher**, not configurable per agent — the dispatcher must know
which events fire which agent, with arguments. A `dispatcher`
trigger_kind in the agent definition only declares "this agent is
hooked into the dispatcher somewhere"; the wiring is in the runtime.

### 6.2 `shell`

Invoked by a shell via the `agent.run` tool. The shell composes
the run's task input (the per-run payload, distinct from the agent's
static system prompt) and receives the structured return (§3.3) when
the run finishes.

> [!class4]
> A shell may only invoke agents whose scoped tool grant is a **subset of the shell's own grant**. A shell cannot escalate by delegating — this is the load-bearing safety property of the authority model. Validated by the dispatcher at `agent.run` execution; rejection is a tool error, not a runtime crash.

### 6.3 `manual`

Invoked by an operator through an API endpoint or UI affordance, with
task input passed in the request. Authority is the calling user's
session. `parent_shell_id` is set to whichever shell the operator
selected as the run's accountable owner (UI requires the selection;
API requires the parameter).

### 6.4 `scheduled`

The scheduler reads the `agents` table for rows with non-null
`schedule` and fires them on cron tick. No parent shell. No task input
beyond what the agent's static prompt already encodes — scheduled
agents are self-contained.

Where the scheduler lives is a runtime detail (a dedicated
`dosarch-scheduler` pm2 app vs. piggy-backing on the dispatcher) and
not pinned by this spec. What the spec pins is: scheduled agents fire
from rows in this table; the same scheduler that runs them is the
single principal for all of them; and they are visible in
`dr_automations` (catalogue-sync, per `agnostic-runtime`'s
infrastructure-catalogue convention).

## 7. Failure handling

The run has four failure modes. Each maps to a row status.

| Failure | Status | Behavior |
|---|---|---|
| Model returns clean text | `ok` | Run completes; `text` and `trace` returned. |
| Tool call fails (handler returns `is_error=true`) | `ok` | Result is recorded in trace; the model may or may not react (depends on `max_turns`); run still completes. **A tool error is not a run error** — it is data the executor/reviewer can read. |
| Hard runtime failure (model unreachable, broker token denied, OOM) | `error` | Row records `error_code` + `error_message`. `text` may be empty; `trace` records partial progress. |
| Per-run timeout exceeded (`timeout_seconds`) OR `max_tool_calls` exceeded | `timeout` | Run aborted at the boundary; partial `trace` recorded; `text` may be empty. |

> [!class3]
> **Why a failed tool is `ok`:** because reviewer-side analysis depends on seeing what the executor *tried*. Demoting a tool failure to a run failure throws that signal away and pushes the substrate toward silent-degradation mode. Operators (and the reviewer model) want visibility, not a stoplight.

**Trace truncation.** A single tool result may be very large
(`file_read` of a big file, `file_search` with many hits). The
runtime applies the same 50KB / 2000-line truncation policy OpenCode
uses, on a per-tool-result basis, and marks the truncated entry
`truncated: true`. The full trace structure is never dropped.

## 8. Bootstrapped agents

Three agents are stood up at substrate bootstrap to satisfy the
`memory-recall.md` spec. Their behavioral specs live in
memory-recall; their structural definitions are listed here so it
is explicit that they conform to this spec.

| Agent | trigger_kind | Pin (initial) | Notes |
|---|---|---|---|
| `summarizer-agent` | dispatcher | small local (TBD) | memory-recall §3.2 |
| `decision-expander-agent` | dispatcher | small local (TBD) | memory-recall §3.2 |
| `recall-agent` | shell | small–mid (TBD) | memory-recall §3.2 + §7.2 |

The specific model pins are a separate operational decision once the
`models` registry has the candidate set seeded. The agents land in
the catalog before the pins are tuned.

## 9. Alpha → beta → release

The user-stated build sequence:

> alpha simple, beta complex, release = unify the two.

This spec lands at **alpha**. The spec is **stable from day one**;
beta and release are **runtime expansions**, not spec rewrites.

| Stage | Runtime behavior | Spec change |
|---|---|---|
| **Alpha** | `max_turns` defaults to 1; runtime honors but emits a warning if any agent declares `max_turns > 1` (multi-turn runtime not yet implemented). All four trigger kinds wired. Three bootstrapped agents online. | This document. |
| **Beta** | Multi-turn runtime lands; `max_turns > 1` is fully honored. Per-turn observability in `trace`. | None — the field already exists. |
| **Release** | Beta defaults become sensible (some agents author-opt in to `max_turns > 1`; the runtime default stays at `1`). Alpha agents still work unchanged. | None — author choice. |

The discipline is that **the asset shape and the table schema do not
change between stages**. What changes is what the runtime does with
them. Agents authored in alpha continue to run unchanged in release.

> [!class4]
> This is the contract that makes "unify the two" achievable rather than a v2-rewrite trap. Any pressure to break it should be resolved by deferring the feature, not by spec-bumping.

## 10. Shell boundaries

Four deliberate constraints, restated together:

1. **Identity is shell-only.** Agents have a `name` (identifying the
   *definition*) and a `run_id` (identifying the *execution*); neither
   is identity in the sovereignty sense (Law 1). Agents do not have
   seed, L&S, current_state, or narrative. They cannot write to
   identity tables — the broker does not mint those scopes.
2. **Memory is shell-only.** A run's trace is recorded in
   `agent_runs`; it is data about what an agent did, not memory the
   agent carries. The next run of the same agent starts from the same
   system prompt, with no awareness of prior runs. Recall across runs
   is the **shell's** job, using the shell's memory protocol
   against `agent_runs` as a data source.
3. **Review is shell-only.** Trace analysis (the "was the executor
   right?" question) is the shell's responsibility. If the shell
   wants a larger model to do that analysis, the shell invokes it —
   the agent runtime does not.
4. **Composition is shell-only.** Sequencing one agent's run into
   another's input, branching on a trace, or repeating a run with
   different parameters — none of these are agent capabilities. They
   are workflows, and workflows live in the shell layer where review
   and authority already do. The substrate has no separate workflow
   primitive (see §1, Where this sits).

These four boundaries are what make agents safe to scale out and
shells worth investing in. Erode any of them and the categories blur.

## 11. Catalogue integration

Agents are catalogued under `dr_*`, alongside skills, tools,
services, etc. — per the `catalogue_sync` pattern. The proposed
addition is a `dr_agents` typed table with the same shape as
`dr_skills` / `dr_tools`. `v_dr_catalogue` projects it. Scheduled
agents additionally surface in `dr_automations` (their cron schedule
is what `dr_automations` already tracks).

This is curated catalogue work — see the `catalogue_sync` skill for
the populator pattern.

## 12. Open questions

Questions worth deciding before beta but **deliberately not decided**
here, because each is a separate decision with its own context:

1. **Per-run task input shape.** Frontmatter does not encode the
   per-run input contract. `shell` and `manual` triggers pass
   arbitrary payloads to the agent; this spec does not require those
   payloads to be schema-validated against the agent definition. A
   `task_input_schema` frontmatter field is a beta enhancement.
2. **Cost ceilings.** `meta.tokens_in / tokens_out` are recorded but
   no per-agent cost cap is enforced. Worth adding once the
   substrate has more than a handful of agents in production.
3. **Test harness.** Regression-testing pinned agents was a stated
   motivator (§1); the harness itself is unscoped here. Likely a
   peer skill / script in `shell_core/scripts/`.
4. **Trigger taxonomy expansion.** Webhook-triggered and
   queue-triggered agents are plausible future trigger kinds. Adding
   one is a `trigger_kind` enum extension, not a spec rewrite.
5. **Scheduler location.** Dedicated pm2 app vs. dispatcher plugin.
   Operational call; this spec does not pin it.

These belong on the agent-spec roadmap, not in this draft.
