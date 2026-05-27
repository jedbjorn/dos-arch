# DOS-Arch — Memory & Recall Spec

Status: Draft — living specification. 2026-05-18.

Peer to `docs/specs/agnostic-runtime.md`. That spec scopes the substrate's
memory design out — "existing and canonical." This spec **is** that redesign:
how a shell's conversation is captured, summarized, and recalled, with the
manual logging burden pulled off the active model and onto programmatic
services and small parallel agents.

It depends on the agnostic-runtime spec for the dispatcher, cold agents,
`chat_messages`, and the `models` registry. It does not restate them.

---

# 1. Purpose and scope #

## Purpose ##

Make a shell's memory **recallable without being a burden to produce.**

Two problems with the memory model inherited from the CLI-shell era:

1. The active chat model is responsible for too many deliberate writes —
   `current_state`, the session narrative, decisions, flags. Every one is a
   manual trigger the model must remember mid-conversation; every one is
   tokens spent not on the user's problem.
2. What gets written is hard to search later. `current_state` is a 280-char
   field that overwrites itself; the narrative is a free-text blob.

The fix: capture everything cheaply and automatically, summarize it with
small parallel models, and expose all of it through one lightweight
`remember` skill. The active model's only judgement-bearing memory act is a
one-line decision marker.

## Scope ##

In scope: the offload model, the session/summary mechanism, the `sessions`
table, the decision-marker flow, the dual-triggered identity skills, the
`remember` skill, and model-job pinning for the memory agents.

Out of scope, owned by the agnostic-runtime spec: the dispatcher, the
`ProviderAdapter` seam, `chat_messages` capture, per-message `body_compact`
compaction, and the `models` registry. Where this spec needs them it points.

## Where this sits ##

dos-arch decomposes AI implementation into four primitives — **model**,
**harness**, **agent**, **shell** (see README). This spec defines how the
**shell** primitive's memory and recall work: capture, summarization, and
recall mechanics that make a shell's history recallable without burdening
the active model. The **agent** primitive is owned by
`docs/specs/cold-agents.md` (this spec uses three named agents — see §2);
the **harness** primitive is owned by `docs/specs/agnostic-runtime.md`
(this spec depends on its dispatcher and `chat_messages` capture).

---

# 2. Terminology #

**"Session" does not mean what it usually means.** It is not a continuous
interactive period and not a resident model process. The term is redefined
here, and the redefinition is the spine of this spec.

| Term | Meaning |
|---|---|
| **Conversation** | One persistent human-facing thread — a `chat_sessions` row plus its `chat_messages`. Long-lived; spans many sessions. (The table name `chat_sessions` predates this spec and is unfortunate — read it as "conversations.") |
| **Session** | **The span of one conversation between two summary checkpoints.** A conversation is an ordered sequence of sessions. Each session, when it closes, is summarized; the summary seeds the next session. One `sessions` row. |
| **Summary checkpoint** | The event that closes a session: a model load/unload swap (local models — forced) or a token-cadence mark (cloud models — chosen). Same event, two triggers. |
| **Provider session** | A model provider's own server-side session/cache feature. Optional, cloud-only, an optimisation — never something the system's correctness depends on. Distinct from a Session above. |
| **summarizer-agent** | A cold agent (defined per `docs/specs/cold-agents.md`) that summarizes a closed session into `sessions.summary`. Dispatcher-triggered; the shell is unaware of it. Pinned to a small model. |
| **decision-expander-agent** | A cold agent that expands a `‹decision›` marker into a full `shell_decisions` record. Dispatcher-triggered; background. Pinned to a small model. |
| **recall-agent** | A cold agent the shell spawns (via `remember`) to search memory and report distilled findings — read-only, possibly fanned out. Runs the search in its own context so the working shell's stays clean. Pinned small–mid. |

A Session is the **summarization unit**. Everything downstream — recall,
the rolling `current_state`, the narrative — is built from sessions.

---

# 3. The offload model #

Every memory write sorts into exactly one of three tiers. The design goal is
to push as much as possible up the table, away from the active model.

## 3.1 The three tiers ##

| Tier | Who writes | What | Cost to the active model |
|---|---|---|---|
| **Programmatic** | the dispatcher / a service | `chat_messages`, token & cost accounting, message indices, the `current_state` mirror | zero |
| **Parallel agent** | summarizer / decision-expander cold agents | session summaries, expanded decision records | zero |
| **Active model** | the shell itself | seed & L&S (identity); a one-line decision marker | one inline marker; identity entries are rare |

The active model's deliberate memory surface drops from seven write targets
(`current_state`, narrative, decisions, flags, connections, seed, L&S) to
**two**: identity entries (seed/L&S — see §6.4) and the decision marker
(§6.3). Neither is an API call mid-conversation.

> [!NOTE] Why not offload everything
> Two things cannot move off the active model. **Identity** (seed, L&S) is
> Law-protected — Laws 2/3/7: a shell curates its own seed and L&S; no other
> agent may author them. **Decision judgement** — *what counts as major* and
> *why* — is the one thing a strong model does well and a small one does not.
> Both stay. The trick is to make them cheap, not to remove them.

## 3.2 The cold agents ##

Three cold agents (defined per `docs/specs/cold-agents.md`) carry the
offloaded work. They divide on **who triggers them** — and that divide
decides what the shell must know about.

| Agent | Triggered by | Shell aware? | Job |
|---|---|---|---|
| **summarizer-agent** | the dispatcher, at a summary checkpoint | **no** — fully background | summarize a closed session → `sessions.summary` |
| **decision-expander-agent** | the dispatcher, harvesting a `‹decision›` marker | **no** — fully background | marker → full `shell_decisions` record |
| **recall-agent** | the shell, via the `remember` skill | **yes** — the shell spawns it, possibly several (§7.2) | search memory → distilled report |

Two trigger paths, deliberately:

- **Service-triggered** — summarizer-agent and decision-expander-agent hook
  to the **dispatcher**, the component that owns the message flow and
  therefore knows when a session closes and when a marked reply lands. They
  run unseen; the shell never spawns them and never waits on them. Offload
  is total.
- **Shell-spawned** — the recall-agent is the one memory act the shell
  *initiates*. The shell must know it exists and be able to spawn it — once,
  or as a bounded fan-out (§7.2). It is a tool the shell reaches for, not a
  background process.

These are the **dispatcher** and **shell** halves of cold-agents.md's
four-trigger taxonomy (§6 — dispatcher / shell / manual / scheduled). All
four trigger kinds produce ephemeral, identity-less, single-task runs;
only the trigger differs.

**Tooling.** A cold agent is not toolless; each needs a scoped grant —

| Agent | Tools |
|---|---|
| summarizer-agent | read a `chat_messages` span; write `sessions.summary` |
| decision-expander-agent | read a marked span; write one `shell_decisions` row |
| recall-agent | read `sessions`, `chat_messages`, `shell_decisions`; no writes |

Grants are **data, not hardcode**: rows in the agnostic-runtime `tools`
registry, assigned the way `shell_tools` assigns tools to shells
(agnostic-runtime §4.2). The cold-agent tuple already carries a `[tool_id]`
list (agnostic-runtime §4.6); these agents' lists are registry rows,
MCP-capable (`tools.kind='mcp'`). The `tools` registry is therefore a
dependency of this spec — see §9.

---

# 4. The session model #

## 4.1 The local-model cycle ##

Local models on constrained VRAM (the design floor is 8 GB — see
agnostic-runtime §9) cannot keep two models resident. The chat model and the
summarizer **compete for the same VRAM**. So a turn on a local model is not a
continuous process; it is a load/unload cycle:

```
load chat model  ->  user message  ->  response
        ->  unload chat model
        ->  load summarizer (gemma / mistral)
        ->  summarize the closing session  ->  write sessions row
        ->  unload summarizer
        ->  load chat model (fresh instance)
        ->  feed prior summary in as context  ->  continue
```

The conversation survives this because it was never in the model — it is in
the DB (`chat_messages`) and the runtime replays it (agnostic-runtime §3.3).
The summary is what makes the *replay cheap*: the fresh instance is seeded
with the prior session's summary rather than the full transcript.

Each load/unload of the chat model is a **session boundary.** This is why
"session" is redefined — for a local model, a session is short and there are
many per conversation.

## 4.2 The cloud-model case ##

A cloud model is not on local VRAM, so nothing *forces* an unload. The system
may then:

- run longer sessions, closing them on a **token-cadence checkpoint** rather
  than a swap; and
- optionally use the provider's own session/cache features (prompt caching,
  server-side sessions) "out of the box" — purely a cost optimisation.

The `sessions` table and the summary mechanism are **identical** for cloud
and local. Only the checkpoint trigger differs: forced swap vs. chosen
cadence. The runtime stays stateless-replay either way; provider sessions, if
used, are an adapter-level optimisation and never a correctness dependency.

## 4.3 Session lifecycle ##

| State | Meaning |
|---|---|
| `open` | The active session — messages are accruing into it |
| `closed` | A checkpoint hit; no more messages; awaiting summary |
| `summarized` | The summarizer has written `summary`; `current_state` mirror updated |

Exactly one `open` session per conversation. Closing one and opening the next
is a programmatic step at the checkpoint — not a model action.

---

# 5. Data model #

Schema deltas against the current `shell_core/schema.sql`. All additions are
nullable or defaulted — additive, no backfill, no rewrite.

## 5.1 sessions (new) ##

The summarization unit. One row per session.

| Column | Type | Notes |
|---|---|---|
| `session_id` | INTEGER PK | |
| `conversation_id` | TEXT FK → chat_sessions | The thread this session belongs to |
| `shell_id` | INTEGER FK → shells | |
| `user_id` | INTEGER FK → users | The FnB |
| `chat_model_id` | INTEGER FK → models | Which chat model ran this session |
| `seq` | INTEGER | Order within the conversation (1, 2, 3…) |
| `start_message_id` | INTEGER FK → chat_messages | First message in the span |
| `end_message_id` | INTEGER FK → chat_messages | Last message in the span |
| `summary` | TEXT | ≤ 400 chars; written by the summarizer; NULL until `summarized` |
| `summary_model_id` | INTEGER FK → models | Which model wrote the summary — supports test-and-pin (§8) |
| `status` | TEXT | `open` / `closed` / `summarized` |
| `opened_at` / `closed_at` / `summarized_at` | TEXT | UTC, server-generated |

The ordered set of a conversation's `sessions` rows **is** the narrative.
The latest `summarized` row's `summary` **is** `current_state`.

## 5.2 shell_decisions — cross-keys (additive) ##

```sql
ALTER TABLE shell_decisions ADD COLUMN conversation_id   TEXT;
ALTER TABLE shell_decisions ADD COLUMN session_id        INTEGER REFERENCES sessions(session_id);
ALTER TABLE shell_decisions ADD COLUMN user_id           INTEGER REFERENCES users(user_id);
ALTER TABLE shell_decisions ADD COLUMN project_id        INTEGER REFERENCES projects(project_id);
ALTER TABLE shell_decisions ADD COLUMN start_message_id  INTEGER REFERENCES chat_messages(message_id);
ALTER TABLE shell_decisions ADD COLUMN end_message_id    INTEGER REFERENCES chat_messages(message_id);
```

A decision becomes queryable by conversation, session, FnB, project, or the
exact message window that produced it. `shell_id` and `parent_decision_id`
are unchanged.

## 5.3 current_state ##

`shells.current_state` stays as a field, but its role changes: it is a
**programmatically-synced mirror** of the latest `summarized` session's
`summary` — the active model never writes it. The cap rises **280 → 400**
chars (the triggers `trg_current_state_cap_*` change the literal). 400 chars
is ~90 tokens — enough for a real index entry, still cheap at every boot.

## 5.4 full_narrative — deprecated ##

`shell_memory_archives.full_narrative` is subsumed by `sessions`. The column
is **not dropped** — the legacy `make launch` boot path still uses it and the
agnostic-runtime spec keeps that path alive during migration. But no new work
writes it; the browser-chat path uses `sessions`.

> [!NOTE] Redundancy retired
> `current_state` (field) and `full_narrative` (blob) were the same job done
> twice — the active model hand-summarising itself. `sessions` replaces both.
> Likewise `chat_sessions` (conversation) and `shell_memory_archives`
> (legacy "session") overlap; new work keys to `chat_sessions`.

---

# 6. Flows #

## 6.1 Capture — programmatic ##

`chat_messages` is written by the dispatcher (agnostic-runtime §3.5) — every
inbound and outbound message, with token/cost accounting. No agent, no model
action. This is the raw record; it is soft-delete only, so nothing is ever
truly lost. Recall always has a floor to fall back to.

## 6.2 Summarize — the summarizer cold agent ##

At a summary checkpoint (§4): the open session is set `closed`; the
summarizer cold agent is dispatched with the message span
(`start`–`end_message_id`); it produces a ≤400-char summary; the row goes
`summarized` and the `current_state` mirror updates. The summarizer is
pinned to a small model (§8). Its summarization call is itself token-logged.

## 6.3 Decide — marker, then expansion ##

The active model does **not** write decision records. When a decision lands
it drops a one-line inline marker in its reply:

```
‹decision› chose X over Y — reason Z
```

Cheap, no API call, hard to forget. A service harvests marked spans; the
**decision-expander** cold agent turns each into a full `shell_decisions`
row — formatting, rationale expansion, and the §5.2 cross-keys (session,
conversation, FnB, project, message window). The active model supplies the
*kernel of judgement*; the cold agent does the *clerical work*.

`--decision` remains as an explicit FnB trigger (see §6.4 on dual triggers).

## 6.4 Identity — dual-triggered skills ##

seed and L&S cannot be offloaded (§3). They are handled by skills, and each
skill carries **two triggers**:

- **Model-initiated** — the skill's description tells the active model it
  *may* fire the skill when a seed-worthy or lesson-worthy moment lands.
- **FnB-initiated** — an explicit command trigger (`--seed`, `--lns`,
  `--decision`) the operator can invoke directly.

The model is never the *single* point of capture — the FnB can always
trigger — but it is empowered to initiate. Belt and suspenders, no friction.
Caps (seed 10, L&S 20) stay trigger-enforced server-side.

---

# 7. The remember skill #

Recall is itself context-hungry — scanning summaries, drilling into raw
windows, weighing candidates all generate intermediate state. Run inline in
the working shell and that search debris lands in the very window the whole
architecture works to keep clean. So `remember` does **not** run inline.

`remember` **dispatches a recall cold agent.** The working shell issues one
call — the query — and gets back one thing: a distilled report. The search
runs in the agent's own ephemeral context and is discarded with it.

## 7.1 The recall agent ##

A cold agent (agnostic-runtime §3.2) with **read-scoped** grants to the
memory tables — `sessions`, `chat_messages`, `shell_decisions` — and no write
path. It:

1. **Searches the index** — `sessions.summary` + `shell_decisions` (text
   match; filterable by date, FnB, project, conversation). Short, dense,
   already-distilled signal.
2. **Drills** into the raw `chat_messages` span behind each candidate.
3. **Judges relevance** — reads the candidate windows and decides which
   actually answer the query. This is the step an inline `LIKE` cannot do.
4. **Reports** in a fixed shape: found / not-found, the session + message
   refs, and the distilled relevant content — never a raw dump.

The working shell's context receives only step 4. Steps 1–3 — the debris —
live and die inside the agent.

## 7.2 Fan-out ##

A wide query ("when did we first discuss X," across months) splits across the
session range: N recall agents, each a slice, each reporting its hits; a
reducer merges. Fan-out is **bounded** — concurrency capped by the
agnostic-runtime tool-concurrency semaphore (§5.2). Parallel search, not
unbounded spawn.

## 7.3 Why this is the retrieval answer ##

Retrieval quality is the system's ceiling — unbounded recall is won or lost
on whether the right thing comes back. An inline `LIKE` returns matches but
cannot tell a real hit from a coincidental keyword. The recall agent reads
and judges: **search narrows, the model decides.** Coarse filter by text
search — `LIKE`, or a SQLite FTS5 index over `sessions.summary` +
`shell_decisions` as a later optimisation; fine filter by the agent's own
relevance pass.

`remember` stays dual-triggered (§6.4) — model- or FnB-initiated — and
lightweight *to invoke*: one call from the working shell. The weight is all
in the agent, off the working context.

---

# 8. Model-job pinning #

Right-sized model for the job. The capability to run powerful local models is
not a reason to use them everywhere — small task, small model.

| Role | Model class | Pin |
|---|---|---|
| Active shell — conversation, judgement, the decision marker | strong (Claude / GPT / Gemini, or a large local model) | `shells.model_id`; per-conversation override |
| Summarizer cold agent | small | gemma or mistral — **test and pin** |
| Decision-expander cold agent | small | clerical/structured output — small; mistral may edge gemma here — test and pin |
| Recall agent — `remember`'s search + relevance pass | small–mid | relevance judgement is more than keyword work, less than the active shell's job — test and pin |

The **mechanism already exists**: `shells.model_id` and the cold-agent tuple
`(task_brief, model_id, …)` (agnostic-runtime §4.6) both carry a model. The
pin is "light" — a config value set after testing, not hardcoded.
`sessions.summary_model_id` records which model actually produced a summary,
so gemma-vs-mistral output can be compared on real data before pinning.

---

# 9. Dependencies #

| Dependency | Why | Status |
|---|---|---|
| **`models`-table reconciliation** | Pinning references `models.model_id`. PR #19 (merged) created `models` as a *local-install inventory*; agnostic-runtime §4.1 defines `models` as the *runtime registry*. Same name, different purpose — they collide. | **Blocking.** Resolve first: rename PR #19's table to an install-inventory, keep `models` as the registry. |
| Cold-agent executor | The summarizer and decision-expander are cold agents. | Delivered by agnostic-runtime Phase 3 (compaction). |
| `tools` / `shell_tools` registry | The cold agents need scoped, data-driven tool grants (§3.2), MCP-capable. Without the registry the grants are hardcoded. | Delivered by agnostic-runtime §4.2 (Phase 1). |
| `chat_messages` capture | The raw floor everything indexes into. | Delivered by the dispatcher (agnostic-runtime). |

---

# 10. Open decisions #

| Question | Why it matters |
|---|---|
| Summary-checkpoint cadence for cloud models — fixed token count, message count, or idle-time? | Sets session length when no VRAM swap forces it |
| Decision-marker syntax — `‹decision›` literal, or a structured tag the dispatcher parses more strictly? | Harvest reliability |
| Does a long cloud session ever need *multiple* summaries, or is one-per-session always enough? | If yes, `sessions` summary becomes 1-to-many |
| `remember` ranking — recency, match score, or both? | Recall quality |
| Recall fan-out (§7.2) — fixed slice count, or adaptive to history length? | Bounds parallel recall-agent spawn |
| Combined identity skill vs. separate `seed` / `lns` skills | Skill ergonomics |

---

# 11. Build sequence #

Slots after agnostic-runtime **Phase 3** — that phase delivers the cold-agent
executor the summarizer and decision-expander run on.

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **M0 — models reconciliation** | Resolve the `models` collision (§9). | One `models` registry; install-inventory renamed. |
| **M1 — sessions table + capture** | `sessions` table; programmatic session open/close at checkpoints; `current_state` becomes the mirror; cap → 400. | A conversation accrues `sessions` rows; `current_state` tracks the latest. |
| **M2 — summarizer** | The summarizer cold agent; pin-test gemma vs mistral. | Closed sessions get summaries automatically. |
| **M3 — decision flow** | The `‹decision›` marker, the harvest service, the decision-expander; `shell_decisions` cross-keys. | A marked decision becomes a fully-keyed record with no active-model API call. |
| **M4 — remember + identity skills** | The `remember` skill + the recall agent (§7); dual-triggered `seed` / `lns` skills; revised `decision` skill. | Recall runs off the working context and returns distilled findings; identity entries dual-triggered. |

**M1–M2** is the minimum that retires `current_state`-as-a-burden. M3–M4
complete the offload and the recall surface.

---

*End of spec.*
