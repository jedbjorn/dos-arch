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
| **Summarizer** | A cold agent (per agnostic-runtime §3.2) that writes session summaries. Pinned to a small model. |
| **Decision-expander** | A cold agent that turns a decision marker into a full `shell_decisions` record. Pinned to a small model. |

A Session is the **summarization unit**. Everything downstream — recall,
the rolling `current_state`, the narrative — is built from sessions.

---

# 3. The offload model #

Every memory write sorts into exactly one of three tiers. The design goal is
to push as much as possible up the table, away from the active model.

| Tier | Who writes | What | Cost to the active model |
|---|---|---|---|
| **Programmatic** | the dispatcher / a service | `chat_messages`, token & cost accounting, message indices, the `current_state` mirror | zero |
| **Parallel agent** | summarizer / decision-expander cold agents | session summaries, expanded decision records | zero |
| **Active model** | the warm shell itself | seed & L&S (identity); a one-line decision marker | one inline marker; identity entries are rare |

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

One lightweight skill, total recall. It is a thin procedure over existing
read paths — no model of its own, runs in the active shell's context.

Two-level search:

1. **Index** — search `sessions.summary` and `shell_decisions` (text match;
   filter by date, FnB, project, conversation). These are short, dense, and
   already the distilled signal.
2. **Archive** — every index row carries a message-id span. Drill from a
   matched summary or decision down to the verbatim `chat_messages`.

"Lightweight to invoke, remember anything that ever happened": the skill
searches the small index; the full raw conversation is always one span-lookup
away because `chat_messages` is never hard-deleted.

> [!NOTE] FTS is deferred
> v1 `remember` runs on `LIKE` / existing content-search endpoints. A SQLite
> FTS5 index over `sessions.summary` + `shell_decisions` is a clean later
> optimisation — the schema does not need it to ship.

---

# 8. Model-job pinning #

Right-sized model for the job. The capability to run powerful local models is
not a reason to use them everywhere — small task, small model.

| Role | Model class | Pin |
|---|---|---|
| Active warm shell — conversation, judgement, the decision marker | strong (Claude / GPT / Gemini, or a large local model) | `shells.model_id`; per-conversation override |
| Summarizer cold agent | small | gemma or mistral — **test and pin** |
| Decision-expander cold agent | small | clerical/structured output — small; mistral may edge gemma here — test and pin |
| `remember` skill | none — runs in the active shell | — |

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
| `chat_messages` capture | The raw floor everything indexes into. | Delivered by the dispatcher (agnostic-runtime). |

---

# 10. Open decisions #

| Question | Why it matters |
|---|---|
| Summary-checkpoint cadence for cloud models — fixed token count, message count, or idle-time? | Sets session length when no VRAM swap forces it |
| Decision-marker syntax — `‹decision›` literal, or a structured tag the dispatcher parses more strictly? | Harvest reliability |
| Does a long cloud session ever need *multiple* summaries, or is one-per-session always enough? | If yes, `sessions` summary becomes 1-to-many |
| `remember` ranking — recency, match score, or both? | Recall quality |
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
| **M4 — remember + identity skills** | The `remember` skill; dual-triggered `seed` / `lns` skills; revised `decision` skill. | Total recall from one skill; identity entries dual-triggered. |

**M1–M2** is the minimum that retires `current_state`-as-a-burden. M3–M4
complete the offload and the recall surface.

---

*End of spec.*
