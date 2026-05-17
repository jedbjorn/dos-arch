---
name: skill_management
description: Skill lifecycle for the substrate — create, update, delete, assign — over the substrate API. Admin-shell only. Interview-driven.
category: workflow
common: 0
---
# skill_management

Create, update, delete, and assign skills over the substrate API. The skill
CRUD endpoints are admin-only — this runs from an admin shell (Sys-Admin).

`$DOS_API_URL` and `$DOS_API_TOKEN` are in your container environment. If a
needed endpoint returns 403, this shell is not an admin shell — surface that
to the operator and stop.

**Trigger:** the operator says create / update / delete / assign a skill.

---

## CREATE

Interview one question at a time: what it does (one-line `description` +
purpose), trigger phrases, args, `category` (workflow / platform / token —
default workflow), `common` (1 = every shell gets it; 0 = assigned
explicitly — substrate-maintenance skills are always 0).

```bash
curl -fsS -X POST "$DOS_API_URL/admin/skills" \
  -H "Authorization: Bearer $DOS_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "<name>", "description": "<desc>", "category": "workflow",
       "content": "<full skill body>", "common": 0}'
```

Returns `{"skill_id": …}`. A 409 means the name is already taken.

---

## UPDATE

```bash
curl -fsS -X PATCH "$DOS_API_URL/admin/skills/<skill_id>" \
  -H "Authorization: Bearer $DOS_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"content": "<new body>"}'
```

Send only the fields that change — `content`, `description`, `category`,
`command`, `common`.

---

## DELETE

```bash
curl -fsS -X DELETE "$DOS_API_URL/admin/skills/<skill_id>" \
  -H "Authorization: Bearer $DOS_API_TOKEN"
```

Soft delete — `is_deleted=1`; the row is preserved and the JOINs filter it
out. Confirm with the operator before deleting.

---

## ASSIGN

Resolve the `skill_id` (`GET /admin/skills/available`) and the target
`shell_id` (`GET /admin/shells`), then:

```bash
# attach
curl -fsS -X POST "$DOS_API_URL/admin/shells/<shell_id>/skills" \
  -H "Authorization: Bearer $DOS_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"skill_id": <skill_id>}'

# detach
curl -fsS -X DELETE "$DOS_API_URL/admin/shells/<shell_id>/skills/<skill_id>" \
  -H "Authorization: Bearer $DOS_API_TOKEN"
```

A newly-attached skill takes effect on the target shell's next session —
the SKILLS block re-renders at boot.

---

## Notes

- `common=1` is for role-agnostic skills every shell should carry.
  Substrate-maintenance skills stay `common=0`, assigned to Sys-Admin.
- A skill's `content` is the full procedure body. Hardcode no absolute host
  paths — shells run in containers and reach memory and state over the API.
