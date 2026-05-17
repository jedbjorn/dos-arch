# dos-arch — CLAUDE.md

Shell-infrastructure substrate. Each shell is a persistent Claude Code agent
with stable identity and its own memory, running in its own rootless-Docker
container as an OS-enforced sandbox. Multi-user at the launcher (scrypt-hashed
passwords); single-user at the API/UI surface (every HTTP request resolves to
`user_id=1`).

A fresh substrate ships two shells: **Sys-Admin** — the resident admin/dev
shell, owned by the first user — and **Forge** (`is_shared=1`), the shared
bootstrap shell that spawns new shells via the `create_shell` skill. A user
with zero owned shells lands in Forge automatically.

The per-shell operating protocol (identity, memory architecture, session
procedures) lives in `shells.system_prompt` and is rendered into the boot
`CLAUDE.md` by `shell_core/scripts/run.py` — don't restate it here.

## Layout

```
shell_core/   api (FastAPI) · ui (SvelteKit) · broker · scripts · assets · templates · schema.sql
docker/       Dockerfiles — dos-shell, dos-broker, dos-api
install/      Rootless-Docker host bootstrap (see install/README.md)
docs/         harness-spec.md
shells/<shortname>/   Per-shell working dirs — managed by run.py, bind-mounted into the container
```

`shell_core/shell_db.db` is the local SQLite store — gitignored, built by
`make bootstrap` from `schema.sql`.

## Auth surface

**Launcher** (`make launch` → `run.py`): username-first; password verified via
scrypt against `users.password_hash` + `users.password_salt`. A user with zero
owned shells skips the password challenge and boots Forge directly to
bootstrap their first shell. Once they own a shell, the password gate engages.

**API + UI** run as `user_id=1`, `is_admin=True` — no login, no api-key check
on the HTTP surface. Bind to localhost, firewall, or put a reverse proxy in
front; the launcher's auth gate does **not** extend to the API. This split is
deliberate — project clones can keep the open API or layer their own auth.

## Run

See **README.md** (Quickstart + Cold bootstrap) and **install/README.md** for
first-time setup. Day-to-day:

```bash
make launch   # auth, pick a shell, boot it in its container
make up       # pm2 starts the UI (the API + broker run as containers)
make health   # GET /health
```
