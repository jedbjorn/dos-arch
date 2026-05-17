---
name: create_shell
description: Forge's tool — interview the operator, then POST /shells to create a new shell with a template-rendered identity, owned by the operator. The new shell plants its own first seed on first boot.
category: workflow
common: 0
---
# create_shell

Forge's one job: create a new shell. Run this end-to-end.

`$DOS_API_URL` and `$DOS_API_TOKEN` are in your container environment.

---

## 1. Identify the operator

Forge is shared — every user can launch it. Read your `## OPERATOR` block,
rendered into this session's CLAUDE.md:

```
## OPERATOR
| **user_id** | `7` |
| **username** | alice |
```

That `user_id` owns the new shell — pass it as `user_id`, the username as
`owner`. If the OPERATOR block is missing, stop and ask the operator to
relaunch Forge from a current substrate.

---

## 2. The interview

Run the whole interview — one block at a time, don't dump every question.

**2a. Identity** — `shortname` (lowercase, 1–8 chars, starts with a letter,
unique, not `forge`), `display_name`, `role` (one phrase), `mandate` (one
sentence).

**2b. Domain & scope** → `domain_and_scope`. What work this shell does;
what is in scope; what is explicitly out; what is deferred and why.

**2c. Operating context** → `operating_context`. Conventions (naming,
branching, definition of done); review preference; coordination with other
shells; tooling quirks.

**2d. Environment** → `connections`. Repos, services, paths — the *map* of
where things live (distinct from 2c's *rules*).

**2e. Skills** — default `common` (every role-agnostic skill). The operator
may name extras, comma-separated (e.g. `common, redline_review`).

---

## 3. Synthesis discipline

The operator's answers are variable; your writing is not. **Normalize, don't
paste** — rewrite answers into tight declarative prose in the operational
blocks' voice. **Follow up, don't guess** — a vague answer gets asked again.
**Resolve contradictions** before writing. The API renders the operational
blocks verbatim; you supply only the two domain sections — a thin interview
can never corrupt the protocol.

---

## 4. Create the shell

One call — the API renders the template, INSERTs the row, attaches skills:

```bash
curl -fsS -X POST "$DOS_API_URL/shells" \
  -H "Authorization: Bearer $DOS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "display_name":      "<display_name>",
        "shortname":         "<shortname>",
        "role":              "<role>",
        "mandate":           "<mandate>",
        "domain_and_scope":  "<2b prose>",
        "operating_context": "<2c prose>",
        "connections":       "<2d prose>",
        "owner":             "<operator username>",
        "user_id":           <operator user_id>,
        "skills":            "common"
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
