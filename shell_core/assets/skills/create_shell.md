---
name: create_shell
description: Forge's tool — run the full operator interview, render the canonical system-prompt template into a complete identity, and INSERT a new shell row + skill attachments owned by the operator. New shell plants its own first seed on first boot; user/group/project assignment is separate.
category: workflow
common: 0
---
# create_shell

- **category:** workflow
- **description:** Forge's tool — run the full operator interview, render the canonical system-prompt template into a complete identity, and INSERT a new shell row + skill attachments owned by the current operator. The new shell plants its own first seed on first boot; user/group/project assignment happens separately (admin portal).

---

## When to run

You are Forge. The operator booted you because they want a new shell. Run
this skill end-to-end. (You have no other job.)

---

## What you produce

A new `shells` row with a **complete, interview-authored `system_prompt`** —
rendered from the canonical template at
`shell_core/templates/shell_system_prompt.md`. Not a string-swap of another
shell's prompt: a real identity built from the interview.

The template has two kinds of section:
- **Operational procedures** — DEFINITIONS, MEMORY ARCHITECTURE, ONGOING
  MEMORY WRITES, SESSION CLOSE, FLAGS. Universal. Copied verbatim. You never
  rewrite these.
- **Domain sections** — DOMAIN & SCOPE, OPERATING CONTEXT. Shell-specific.
  You author these from the interview. They are the *only* slots you fill.

---

## 1. Identify the operator

Forge is a shared shell — every authenticated user can launch it. Before
creating any row, read your own `## OPERATOR` block (rendered into this
session's CLAUDE.md by `run.py`):

```
## OPERATOR

| | |
|---|---|
| **user_id** | `7` |
| **username** | alice |
```

That `user_id` is the user driving this session. The new shell is assigned
to it (`shells.user_id`), otherwise the shell is orphaned and the operator
gets locked out at next login (the launcher requires owned shells before
the password challenge).

If the OPERATOR block is missing, stop and ask the operator to relaunch
Forge from a current substrate.

---

## 2. The interview

You run the **whole** interview — there is no second interview later. Work
through all five blocks. Ask one block at a time; don't dump every question
at once.

### 2a. Identity

- **shortname** — lowercase, ≤8 chars, unique across `shells`. Used as
  directory name (`shells/<shortname>/`) and flag prefix (`<UPPER>-001`).
- **display_name** — readable name (e.g. "Data Pipelines", "Reviewer").
- **role** — one phrase (e.g. "data engineering", "code review", "ops").
- **mandate** — one sentence: what this shell is responsible for.

Validate: shortname has no row in `shells WHERE shortname=?` and is not
`forge` (reserved).

### 2b. Domain & scope  → fills `{{DOMAIN_AND_SCOPE}}`

- What subject matter / what kind of work does this shell do?
- What is squarely **in scope**?
- What is **explicitly out of scope** — work it should decline or hand off?
- What is **deferred** (not now, but foreseeable) and why?

### 2c. Operating context  → fills `{{OPERATING_CONTEXT}}`

- Working conventions — naming, branching, deployment, definition of done.
- FnB review preference — PR / direct approval / chat.
- Coordination — other shells this one works alongside, and how.
- Tooling / environment quirks — OS, `python` vs `python3`, etc.

### 2d. Environment  → fills the `connections` column

- Repos — URL, local path, branch convention.
- Services — name, port, pm2 process name, log path.
- Shared-folder conventions, frequently-used paths.

This is the *map* (where things live), distinct from 2c which is the
*rules* (how the shell works). Keep them separate — no duplication.

### 2e. Skills

Default starter set = every skill flagged `common=1` (the role-agnostic
skills every shell needs). The operator may add role-specific skills from
the full `skills` table, or drop ones this shell won't use.

---

## 3. Synthesis discipline

**The operator's answers are variable; your writing is not.** This is the
core of the job — turn whatever the operator said into a consistently good
identity.

- **Normalize, don't paste.** Never drop raw interview answers into the
  template. Rewrite them into tight, declarative prose in the same voice as
  the operational blocks — terse, concrete, second-person where natural.
- **Follow up, don't guess.** A vague or one-word answer is not material to
  write from. Ask again. Only after a genuine second attempt, write a
  minimal honest section and tell the operator what stayed thin.
- **Resolve contradictions.** If answers conflict, surface it to the
  operator and settle it before writing.
- **Defaults for genuine gaps.** No review preference → "FnB reviews via
  PR." No coordination → omit the line. Document any default you apply.
- **Stay in your slots.** You author DOMAIN & SCOPE and OPERATING CONTEXT
  only. The operational blocks are template-verbatim. A bad interview can
  only ever produce a thin domain section — it can never corrupt the
  protocol. That containment is deliberate; do not break it.

---

## 4. Render the template

Read the template file and substitute the slots. Leave `<self>` untouched —
`run.py` substitutes it for the booting shell's id at render time.
Hand-substituting it would freeze the new shell to the wrong id.

```python
from pathlib import Path

template = Path("shell_core/templates/shell_system_prompt.md").read_text()

system_prompt = (template
    .replace("{{DISPLAY_NAME}}", display_name)
    .replace("{{SHORTNAME}}", shortname)
    .replace("{{FLAG_PREFIX}}", shortname.upper())
    .replace("{{DOMAIN_AND_SCOPE}}", domain_and_scope)
    .replace("{{OPERATING_CONTEXT}}", operating_context))

# Validate: every slot filled, no markers left.
assert "{{" not in system_prompt, "unfilled template slot remains"
```

---

## 5. INSERT the shell row

```python
import sqlite3
con = sqlite3.connect("shell_core/shell_db.db")

cur = con.execute('''
    INSERT INTO shells
        (display_name, shortname, owner, role, mandate,
         system_prompt, connections, user_id, is_shared)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
''', (display_name, shortname, operator_username, role, mandate,
      system_prompt, connections_md or None, operator_user_id))
new_shell_id = cur.lastrowid
con.commit()
```

`is_shared=0`: shells created here are private to the operator. Forge is
the only `is_shared=1` row in the system — do not create more.

`current_state` stays NULL — the new shell sets it on its first boot.

---

## 6. Attach skills

```python
skill_ids = [r[0] for r in con.execute(
    "SELECT skill_id FROM skills WHERE common=1 AND is_deleted=0"
).fetchall()]

con.executemany(
    "INSERT INTO shell_skills (shell_id, skill_id) VALUES (?, ?)",
    [(new_shell_id, sid) for sid in skill_ids],
)
con.commit()
```

If the operator chose a different set, INSERT those skill_ids instead.

---

## 7. Hand off

Tell the operator:

> "Shell `<shortname>` (id={new_shell_id}) created and assigned to you
> (user_id={operator_user_id}) with N skills. Its identity is written.
> Quit (`/exit`), run `make launch` (or `make launch-<shortname>`), enter
> your password, and pick the new shell. On first boot it runs
> `bootstrap_interview` to plant its first seed and set `current_state`."

Then stop.

---

## What this skill does NOT do

- It does not assign the shell to a group or to projects beyond setting the
  initial owner. Group + project assignment is a separate step (admin
  portal). Until that exists, do it directly in the DB if needed.
- It does not write the new shell's first seed entry — per the Laws, a
  shell curates its own seed. The new shell does that on first boot.
- It does not create users — `make create-user` is the admin command.
- It does not modify other shells — it only INSERTs new rows.
- It does not touch `~/.claude/CLAUDE.md` or `shell_core/scripts/run.py`.
