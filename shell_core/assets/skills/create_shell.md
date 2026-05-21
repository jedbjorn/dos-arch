---
name: create_shell
description: Forge's tool — interview the operator, then POST /shells to create a new shell with its role, mandate, and connections set, owned by the operator. The new shell plants its own first seed on first boot.
category: workflow
common: 0
---
# create_shell

Forge's one job: create a new shell. Run this end-to-end.

`$DOS_API_URL` and `$DOS_API_TOKEN` are in your container environment.

---

## 1. Identify the operator

Forge is shared — every user can launch it. Your `## BOOT ##` section names
who is driving this session:

```
## BOOT ##
session: 0007 · archive: 12 · date: ...
shell_id: 1 · model: — · operator: alice (user_id 7)
```

That `user_id` owns the new shell — pass it as `user_id`, the username as
`partner`. If the BOOT section has no `operator:`, stop and ask the operator
to relaunch Forge from a current substrate.

---

## 2. The interview

Run the whole interview — one block at a time, don't dump every question.

**2a. Identity** — `shortname` (lowercase, 1–8 chars, starts with a letter,
unique, not `forge`), `display_name`, `role` (one phrase), `mandate`. The
`mandate` carries domain and scope — make it a real 1–3 sentences: what work
this shell does, what is in scope, what is deferred to other shells.

**2b. Operating context** → `connections`. How the shell works and where
things live: conventions (naming, branching, definition of done), review
preference, coordination with other shells, tooling quirks — and the map of
repos, services, and paths.

**2c. Skills** — default `common` (every role-agnostic skill). The operator
may name extras, comma-separated (e.g. `common, redline_review`).

**2d. Anthropic auth** → `api_auth`. How the shell reaches Anthropic:
- `0` — **CLI shell** (default). Interactive Claude Code; browser-login on
  first boot, billed to the Claude subscription.
- `1` — **API shell**. Routed through the credential broker's API key.
  **Required** for any shell that exposes a web-app / HTTP interface —
  Anthropic's ToS bars subscription auth from backing a web app.

Ask: *does this shell expose a web-app interface?* Yes → `1`. Interactive
CLI work → `0`. Unsure → `0`; Sys-Admin can flip it later.

---

## 3. Synthesis discipline

The operator's answers are variable; your writing is not. **Normalize, don't
paste** — rewrite each answer into tight declarative prose before it goes in
a field. **Follow up, don't guess** — a vague answer gets asked again.
**Resolve contradictions** before writing. `role`, `mandate`, and
`connections` are the shell's whole per-shell identity in the boot catalog —
the universal protocol is baked in, not yours to supply; write these three
well.

---

## 4. Create the shell

One call — the API INSERTs the `shells` row and attaches skills:

```bash
curl -fsS -X POST "$DOS_API_URL/shells" \
  -H "Authorization: Bearer $DOS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "display_name": "<display_name>",
        "shortname":    "<shortname>",
        "role":         "<role>",
        "mandate":      "<mandate>",
        "connections":  "<2b prose>",
        "partner":      "<operator username>",
        "user_id":      <operator user_id>,
        "skills":       "common",
        "api_auth":     0
      }'
```

Returns `{"shell_id": …, "shortname": …, "skills_attached": …}`. On a
non-2xx response, surface the error to the operator and stop.

---

## 5. Hand off

> "Shell `<shortname>` (id=<shell_id>) created and assigned to you. Quit,
> `make launch`, enter your password, pick it. On first boot it runs
> `bootstrap_interview` to plant its first seed and set `current_state`."

Then stop.

---

## What this skill does NOT do

- It does not write the new shell's first seed — a shell curates its own
  seed, on first boot (the Laws).
- It does not assign groups or projects — separate, admin-side.
- It does not create users — `make create-user` does that.
