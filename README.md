# dos-arch

Shell-infrastructure substrate for running persistent Claude Code "shells"
on a single host — each shell in its own rootless-Docker container as an
OS-enforced sandbox. A shell is an AI agent with stable identity, its own
memory, and a workspace directory. The substrate handles authentication,
identity rendering, session management, the SQLite-backed memory store
that keeps a shell coherent across runs, and a credential broker that lets
shell containers run without secrets of their own.

dos-arch is the dockerized, Arch-host variant of the substrate.

This README is a tour of how it works. If you want to read code: the
launcher (`shell_core/scripts/run.py`) is the load-bearing piece — it ties
everything together.

---

## Dependencies

The substrate runs on a handful of host packages. **[Quickstart Step 0](#quickstart)**
below has the install commands — this is what each one is for:

- **git**, **make** — clone the repo + Make entry points
- **Python 3.10+** — FastAPI runtime, launcher, admin scripts
- **Node 18+** + **npm** — SvelteKit UI
- **pm2** — process manager for the host-level UI (the API and broker run
  as their own containers)
- **Docker** + `docker-buildx`, `slirp4netns`, `fuse-overlayfs` — the
  per-shell container sandbox (run rootless)
- **acl** (`setfacl`) — lets the `dos-arch` service user reach the clone

`claude` is **not** a host dependency — it is baked into the `dos-shell`
image and run via `docker exec` inside the container.

Installing the packages is only the start: the **rootless-Docker
configuration** — service user, rootless daemon, the substrate images — is
the scripted procedure in **[install/README.md](install/README.md)**. Those
scripts are Arch-specific (`pacman`); on Ubuntu the rootless-Docker steps
need adapting.

> **Next:** **[install/README.md](install/README.md)** for the Docker host,
> then **Cold bootstrap** below for the substrate.

---

## Quickstart

The system has two layers, documented in two files. The real end-to-end
sequence — fresh host → working shell — runs top to bottom: copy each
command in turn, one at a time. The links go to deeper explanation; you
do not need to follow them to get through the install.

### Step 0 — dependencies & clone (operator)

The whole install runs on a handful of host packages. **Install them
first** — a skipped dependency doesn't fail loudly here; it surfaces much
later as a `<name> not found` error (`pm2 not found`, `node not found`, …).
See **[Dependencies](#dependencies)** above for what each one does.

**Arch / CachyOS:**

```bash
sudo pacman -Syu     # rolling distro — sync the package db first, or pacman -S 404s on stale entries
sudo pacman -S --needed git base-devel python nodejs npm docker docker-buildx slirp4netns fuse-overlayfs acl
sudo npm install -g pm2
```

If `pacman -Syu` updates the kernel, reboot before continuing.

**Ubuntu (24.04+):**

```bash
sudo apt update
sudo apt install -y git build-essential python3 python3-venv nodejs npm docker.io docker-buildx slirp4netns fuse-overlayfs uidmap acl
sudo npm install -g pm2
```

Then clone the repo into your home directory:

```bash
git clone https://github.com/jedbjorn/dos-arch.git ~/dos-arch
```

### Layer 1 — Docker host

Detailed in **[install/README.md](install/README.md)**.

#### 1 — host bootstrap (operator)

Run from your clone, as the operator:

```bash
cd ~/dos-arch
```

```bash
sudo ./install/host-setup.sh
```

[Creates the `dos-arch` service user, subuid/subgid ranges, installs `docker docker-buildx slirp4netns fuse-overlayfs`, disables the rootful daemon, enables linger, stages `install/`+`docker/` into `~dos-arch/setup/`.](install/README.md#1--host-bootstrap-operator-sudo)

#### 2 — rootless Docker (dos-arch)

Enter a `dos-arch` session (run as the operator):

```bash
sudo machinectl shell dos-arch@
```

Inside that session the staged setup lives in `~/setup`:

```bash
cd ~/setup
```

```bash
./install/rootless-setup.sh
```

Then return to your operator login:

```bash
exit
```

[Fetches version-matched rootless-extras, runs the setuptool, persists `PATH`+`DOCKER_HOST` in `.bashrc`, verifies with `docker run hello-world`.](install/README.md#2--rootless-docker-as-dos-arch)

#### 3 — create `.env` + grant access (operator)

Back as the operator, in your clone:

```bash
cd ~/dos-arch
```

```bash
cp .env.example .env
```

Fill in the two broker secrets — `ANTHROPIC_API_KEY` and `GITHUB_TOKEN`:

```bash
nano .env
```

Then grant the `dos-arch` user access to the clone:

```bash
setfacl -m u:dos-arch:x ~
```

```bash
setfacl -R -m u:dos-arch:rwX ~/dos-arch
```

```bash
setfacl -R -d -m u:dos-arch:rwX ~/dos-arch
```

[Broker secrets; grants `dos-arch` access to the clone.](install/README.md#3--create-env-operator) The linked section walks through obtaining each token.

#### 4 — build images (dos-arch)

`build-image.sh` and `broker-up.sh` need the full clone, so enter a `dos-arch` session that lands in it (run as the operator):

```bash
sudo machinectl shell dos-arch@ /bin/bash -lc "cd $HOME/dos-arch && exec bash -l"
```

Then build all three images:

```bash
./install/build-image.sh
```

[Builds 3 images: `dos-shell`, `dos-broker`, `dos-api`.](install/README.md#4--build-images--start-the-broker-as-dos-arch)

#### 5 — start the broker (dos-arch)

In the same `dos-arch` session:

```bash
./install/broker-up.sh
```

[Creates `dos-net`, runs the `dos-broker` container, health-checks it.](install/README.md#4--build-images--start-the-broker-as-dos-arch)

Then return to your operator login:

```bash
exit
```

### Layer 2 — substrate

Detailed in **[Cold bootstrap](#cold-bootstrap)** below.

#### Refresh the clone (operator)

You own the clone, so the `git pull` is yours to run:

```bash
cd ~/dos-arch
```

```bash
git pull
```

[Refreshes the Layer-1 clone before building the substrate.](#cold-bootstrap)

#### 6 — install dependencies (dos-arch)

Steps 6–11 run in **one `dos-arch` session** — once you are in, copy them
straight down the list. Enter it from your operator login:

```bash
sudo machinectl shell dos-arch@ /bin/bash -lc "cd $HOME/dos-arch && exec bash -l"
```

Then:

```bash
make install
```

[`.venv` + pip (fastapi/uvicorn/pydantic) + `npm install` in `ui/`.](#cold-bootstrap)

#### 7 — bootstrap the database (dos-arch)

In the same session:

```bash
make bootstrap
```

[`bootstrap.py`: applies `schema.sql`, seeds skills from `assets/skills/`, seeds Forge, prompts for the first user, seeds Sys-Admin → writes `shell_db.db`.](#cold-bootstrap) This step is interactive — it prompts for the first user's username and password.

#### 8 — start the API (dos-arch)

`api-up.sh` needs `shell_db.db`, so it runs *after* `make bootstrap`. Same session:

```bash
./install/api-up.sh
```

[Runs the `dos-api` container, bind-mounts `shell_core/`, publishes `127.0.0.1:8000`.](#cold-bootstrap)

#### 9 — start the UI (dos-arch)

```bash
make up
```

[pm2 starts the UI (`127.0.0.1:5173`).](#cold-bootstrap)

#### 10 — launch a shell (dos-arch)

```bash
make launch
```

[`run.py`: auth → picker → render `CLAUDE.md` → `ensure_container` → `docker exec -it claude` into `shell-<name>`.](#cold-bootstrap)

#### 11 — install the catalogue cron (dos-arch)

```bash
./install/cron-install.sh
```

[Installs the daily dr_* catalogue sync cron — the only *automatic* full sync; logs each run to `dr_sync_runs`. Run once.](#cold-bootstrap)

That is the full install. From here, `make launch` (step 10) is the daily
entry point — see **[Daily commands](#daily-commands)** below.

### Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `pm2 not found` / `node not found` / `python3 not found` (from `make install`) | A dependency was skipped — run **Step 0** above, then retry. |
| `failed retrieving file …` (during `host-setup.sh`) | Stale package database on a rolling distro — `sudo pacman -Syu` (reboot if the kernel updates), then re-run the step. |
| `docker: command not found` (`build-image.sh` / `api-up.sh` / `make launch`) | Not in a `dos-arch` session, or its `PATH` isn't loaded — use the `sudo machinectl shell dos-arch@ /bin/bash -lc "…"` one-liner forms; the `-l` login shell loads `~/.bashrc`. |
| `sudo` asks for a `dos-arch` password | You ran `sudo` *inside* a `dos-arch` session — `dos-arch` is passwordless and not a sudoer. `exit` to the operator first; `sudo` is the operator's. |

### Updating procedure

Routine updates need no rebuild — the API and UI run from bind-mounted
source, so a `git pull` plus a restart picks up code changes.

#### U1 — refresh the clone (operator)

```bash
cd ~/dos-arch
```

```bash
git pull
```

#### U2 — restart services (dos-arch)

Enter a `dos-arch` session in the clone (run as the operator):

```bash
sudo machinectl shell dos-arch@ /bin/bash -lc "cd $HOME/dos-arch && exec bash -l"
```

Recreate the API container against the updated source:

```bash
./install/api-up.sh
```

Bounce the UI:

```bash
make restart
```

Then return to your operator login:

```bash
exit
```

Before an update that includes a schema change, snapshot the DB first —
`make db-backup`, run in the same `dos-arch` session.

#### Rebuilding images (when Dockerfiles change)

The images only need rebuilding when something under `docker/` changes — or
to pin a new Claude Code version into `dos-shell`. In the same `dos-arch`
session as U2:

```bash
./install/build-image.sh
```

```bash
./install/broker-up.sh
```

Existing shell containers keep running their old `dos-shell` image until
they are recreated.

### Teardown procedure

`teardown.sh` is the inverse of the install — it runs in three phases. Full
detail in **[install/README.md](install/README.md#teardown--rebuild-or-complete-removal)**.

#### T1 — dos-arch-side teardown (dos-arch)

Enter a `dos-arch` session (run as the operator):

```bash
sudo machinectl shell dos-arch@
```

The staged scripts live in `~/setup`:

```bash
~/setup/install/teardown.sh
```

Then return to your operator login:

```bash
exit
```

Prunes all containers / images / networks / volumes and uninstalls rootless
Docker.

#### T2 — host-level removal (operator, sudo)

As the operator, remove the `dos-arch` service user and its host footprint:

```bash
sudo loginctl disable-linger dos-arch
```

```bash
sudo loginctl terminate-user dos-arch
```

```bash
sudo userdel -r dos-arch
```

```bash
sudo sed -i '/^dos-arch:/d' /etc/subuid /etc/subgid
```

Optional — remove the Docker packages, only if nothing else on the host
uses them (`pacman` refuses if a package still has dependents):

```bash
sudo pacman -Rns docker docker-buildx slirp4netns fuse-overlayfs
```

To rebuild from here, stop — the host is clean — and start again at
**[step 1](#1--host-bootstrap-operator)**.

#### T3 — complete removal (operator)

Phases T1–T2 leave your clone and shell config untouched. For a complete
rip-out, also remove these — as the operator:

```bash
setfacl -b ~
```

```bash
rm -rf ~/dos-arch
```

```bash
sudo rm -f /etc/sudoers.d/launch-dos-arch
```

```bash
rm -rf ~/db_backups/dos-arch
```

Then remove the `launch-dos-arch` shortcut from your shell — see
**[install/README.md](install/README.md#teardown--rebuild-or-complete-removal)**
for the fish/bash specifics.

`~/dos-arch/.env` held real credentials (`ANTHROPIC_API_KEY`,
`GITHUB_TOKEN`) — rotate them if the host is shared or untrusted. Deleting
the file clears it from disk, not from anywhere it was already used.

---

## Daily commands

```bash
sudo machinectl shell dos-arch@ /bin/bash     #Enter the shell env

make launch                                   # picker: auth, pick a shell, launch it in its container
make launch-<shortname>                       # boot that shell directly (skip picker)
make create-user                              # provision a new substrate user
make set-password                             # reset a user's launcher password
make up                                       # pm2 start the UI (API + broker run as containers)
make down                                     # pm2 delete the UI
make restart                                  # bounce the UI
make status                                   # pm2 ls
make logs                                     # pm2 logs (Ctrl-C to detach)
make health                                   # GET /health
make db-backup                                # snapshot shell_db.db -> ~/db_backups/dos-arch/<ts>.db
make bootstrap                                # one-shot fresh-substrate setup; refuses if DB exists
make db-sync                                  # refresh the catalogue (dr_*) from current substrate state
make catalogue                                # print the catalogue (filter via ARGS=, e.g. ARGS='flag')
```

`make launch` runs as the `dos-arch` service user — it drives rootless
Docker. Use the `launch-dos-arch` shortcut below to launch from your own
login.

### Shortcut: `launch-dos-arch` / 'enter-dos-arch'

The launcher runs as the `dos-arch` service user — it drives rootless
Docker, which only `dos-arch` can reach. `launch-dos-arch` is a shortcut,
defined in your operator login's shell, that hops into a `dos-arch` session
and runs `make launch` from any directory.

The functions use `$HOME/dos-arch` — your shell expands `$HOME` *before*
entering the `dos-arch` session, so the session receives your real clone
path. (Inside a `dos-arch` session `~` is `/home/dos-arch`, not your home —
which is why the path can't be written `~/dos-arch` here.) Change it only if
you cloned somewhere other than `~/dos-arch`.

**fish** — define a function and persist it (`funcsave` writes it to
`~/.config/fish/functions/`, so it survives new sessions):

**Enters the Dos-arch dir**
```fish
function enter-dos-arch
    sudo machinectl shell dos-arch@ /bin/bash -lc "cd $HOME/dos-arch && make launch"
end
funcsave enter-dos-arch
```

**Launches the Shell Renderer**
```fish
function launch-dos-arch
    sudo machinectl shell dos-arch@ /bin/bash -lc "cd $HOME/dos-arch && make launch"
end
funcsave launch-dos-arch
```

**bash** — add a function to `~/.bashrc` (a function, not an alias — it
nests quotes cleanly):

**Enters the Dos-arch dir**
```bash
cat >> ~/.bashrc <<'EOF'
enter-dos-arch() { sudo machinectl shell dos-arch@ /bin/bash; }
EOF
source ~/.bashrc
```
**Launches the Shell Renderer**
```bash
cat >> ~/.bashrc <<'EOF'
launch-dos-arch() { sudo machinectl shell dos-arch@ /bin/bash -lc "cd $HOME/dos-arch && make launch"; }
EOF
source ~/.bashrc
```

Then `launch-dos-arch` boots the picker from anywhere. It prompts once for
your `sudo` password per launch.

**Drop the password prompt (optional).** A scoped `sudoers` rule lets the
hop run without a prompt — no new privilege, since your operator user is
already a sudoer. As that user (replace `<operator>` with your username):

```bash
echo '<operator> ALL=(root) NOPASSWD: /usr/bin/machinectl shell dos-arch@*' \
  | sudo tee /etc/sudoers.d/launch-dos-arch
sudo chmod 440 /etc/sudoers.d/launch-dos-arch
```

---

## Cold bootstrap

Fresh host to working substrate. Two layers:

**1. Rootless-Docker host** — covered by `install/README.md`: a `dos-arch`
service user, rootless Docker, and the `dos-shell`, `dos-broker`, and
`dos-api` images. This is the sandbox layer — every shell runs in a
container built from the `dos-shell` image, the `dos-broker` container
holds credentials so the shell containers don't have to, and the `dos-api`
container serves the substrate memory API.

**2. The substrate** — the DB, the `dos-api` container, and the host-level
UI. You already cloned the repo in Layer 1 (Quickstart step 0); this
continues from that clone — no second clone.

First, **as the operator**, refresh it:

```bash
cd ~/dos-arch && git pull
```

Now open a `dos-arch` session for the build. **Run this from your operator
login** — your normal shell, prompt showing your own username. If the prompt
shows `dos-arch@…` you are still in a `dos-arch` session from Layer 1: type
`exit` first, or `sudo` asks for a `dos-arch` password that does not exist
(`dos-arch` is passwordless and not a sudoer). The one-liner drops you into a
fresh session already sitting in your clone — `$HOME` expands in *your* shell
first, so it lands in the right directory:

```bash
sudo machinectl shell dos-arch@ /bin/bash -lc "cd $HOME/dos-arch && exec bash -l"
```

It prompts once for **your** password. Inside that `dos-arch` session, build
the substrate:

```bash
make install              # python venv + pip + npm
make bootstrap            # schema + skills + Forge + first user + Sys-Admin (interactive)
./install/api-up.sh       # start the dos-api container (needs shell_db.db)
make up                   # pm2 starts the UI (127.0.0.1:5173)
make launch               # auth, then picker
```

`api-up.sh` runs as the `dos-arch` service user (it drives rootless
Docker). It (re)starts the `dos-api` container on `dos-net`, bind-mounts
`shell_core/`, and publishes the API on `127.0.0.1:8000` — so a `git pull`
plus a re-run updates the API with no rebuild.

`make bootstrap` runs `shell_core/scripts/bootstrap.py`, which:
1. Errors out if `shell_db.db` already exists (use `make db-backup` first if recreating).
2. Executes `schema.sql` against a new SQLite file.
3. Seeds every skill from `shell_core/assets/skills/` — one tracked `.md` per skill, frontmatter + body.
4. Seeds Forge, the shared bootstrap shell, from `shell_core/assets/shells/forge.md` (`is_shared=1`, `create_shell` attached).
5. Prompts for the first user — username + password. This is the substrate admin.
6. Seeds Sys-Admin, the resident admin/dev shell, owned by that user — system prompt rendered from `shell_core/templates/shell_system_prompt.md`, with every `common`-flagged skill attached.

So a freshly-bootstrapped substrate already has a working admin shell. On
`make launch` the first user enters their username, clears the password
challenge, and picks Sys-Admin — or Forge, to spawn more shells.

**The launcher self-heals.** On every `make launch`, `run.py` calls
`ensure_forge(conn)`. If the Forge row is missing — accidentally deleted,
clone restored from backup, partial DB — it's re-seeded transparently
before auth runs. So Forge is always present at boot. Only a missing DB
file requires `make bootstrap`.

Subsequent users are added with `make create-user`. A user with zero
owned shells skips the password challenge and boots straight into Forge,
where `create_shell` interviews them and spawns their first shell.

---

## How users work

`users` is the only auth surface; the API/UI runs single-user (every
HTTP request resolves to `user_id=1`, `is_admin=True`). The launcher gate
does **not** extend to the API — bind to localhost, put a reverse proxy in
front, or accept the open-localhost contract.

**Password hashing.** scrypt with `N=16384`, `r=8`, `p=1`, 16-byte
salt, 32-byte derived key. Stored as base64 in `users.password_hash` +
`users.password_salt`. See `shell_core/scripts/run.py`.

**Auth flow** (launcher):

```
username → lookup_user(con, username)
            ↓
    ┌─ user has zero owned shells → skip password, return (user, verified=False)
    │                                                ↓
    │                                       drops into Forge to bootstrap
    │
    └─ user owns ≥1 shell → prompt for password → verify → return (user, verified=True)
                                                              ↓
                                                       picker (owned ∪ shared)
```

The zero-owned-shells exemption is what makes self-service bootstrap work:
a freshly-created user can authenticate on username alone, just enough to
reach Forge and create their first shell. Once they own one, the password
gate engages permanently.

**Admin commands:**
- `make create-user` — interactive: username, password, initials, email.
- `make set-password` — reset an existing user's password.

Both are thin wrappers around scripts in `shell_core/scripts/`.

---

## Repo layout

```
shell_core/
  api/                    FastAPI substrate (routers: shells, users, skills, flags, admin)
  ui/                     SvelteKit substrate UI (routes: /shells, /flags, /plans)
  broker/                 Credential broker — egress proxy; injects auth so shell containers run credential-free
  schema.sql              Canonical SQLite schema (~25 tables + triggers + 2 catalogue views)
  shell_db.db             Local SQLite store — gitignored, built via `make bootstrap`
  shell_db.py             Connection helper used by api/common/db.py
  scripts/run.py          Launcher: auth → picker → render CLAUDE.md → docker exec claude
  scripts/bootstrap.py    One-shot bootstrapper — `make bootstrap`
  scripts/db_init.py      Seeding library — seed_skills / ensure_forge / seed_sys_admin
  scripts/dr_sync.py      Catalogue populator — wired sync targets + dispatcher
  scripts/catalogue.py    `make catalogue` — print the catalogue grouped by ref_table
  scripts/create_user.py / set_password.py  Admin scripts for users
  assets/                 Seed data — skills/*.md + shells/{forge,sys-admin}.md
  templates/              boot.md (preamble) + shell_system_prompt.md (new-shell template)
  migrations/             Historical migrations — schema.sql is now canonical; migrations are reference
docker/
  shell/                  Dockerfile for the dos-shell image — one container per shell instance
  broker/                 Dockerfile for the dos-broker image — the credential broker
  api/                    Dockerfile for the dos-api image — the substrate memory API
install/                  Rootless-Docker host bootstrap — host-setup / rootless-setup / build-image / broker-up / api-up / cron-install / teardown (see install/README.md)
docs/                     harness-spec.md — the harness specification
shells/<shortname>/       Per-shell working dirs (managed by run.py; CLAUDE.md regenerated each session; bind-mounted into the shell's container as /workspace)
.env.example              Template for .env — broker secrets (ANTHROPIC_API_KEY, GITHUB_TOKEN); .env is gitignored
ecosystem.config.cjs      pm2 process map (UI on 5173; API + broker run as containers)
Makefile                  Entry points: install, bootstrap, db-sync, db-backup, catalogue, launch, up/down/health
```

---

## What's in the database

`shell_core/shell_db.db` is local-only (not in git). `shell_core/schema.sql`
is the canonical schema. Tables, grouped by purpose:

**Identity**
- `users` — username, scrypt password hash + salt, theme prefs.
- `shells` — one row per shell. Identity columns + `system_prompt` + `current_state` + `connections` + `is_shared` + `user_id` (owner).
- `shell_identity_entries` — seed and L&S entries, one row each. Caps enforced by triggers.
- `shell_decisions` — major decisions log. Append-only; supersede via `parent_decision_id`.

**Sessions & narrative**
- `shell_memory_archives` — one row per session. `full_narrative` accumulates throughout.
- `chat_sessions` / `chat_messages` — UI-side chat history (separate from the per-shell session log).

**Skills**
- `skills` — skill definitions: `name`, `description`, `category`, `content`. The content is the full procedure body, lazy-loaded.
- `shell_skills` — many-to-many: which skills are attached to which shell. Drives the `## SKILLS` block at boot.

**Projects**
- `projects` — `shortname`, `title`, `purpose`, `standing`, `status`.
- `project_shells` — assignment of a project to a shell, with a `role`.

**Tracking**
- `flags` — open/resolved blockers, with priority and `parent_flag_id` for hierarchies.
- `plans` — multi-step plan documents (draft / active / complete / abandoned).

**Inter-shell + automation**
- `shell_messages` — messages between shells.
- `shell_prompt_automations` — recurring prompts.
- `shell_logs` — execution logs.

**Audit**
- `app_ui_logs` — every API/UI request (method, path, status, duration, user, shell).

**The catalogue** (`dr_*` family + `shell_dr_link` + 2 views) — a live
index of substrate components (routes, routers, deps, libs, services,
repos, files, automations, env vars). Auto-syncs on API restart. Each row
carries `name` + `description_short` (≤100 chars) for fast lookup. See the
**The catalogue** section below for the full architecture.

Triggers worth knowing about:
- `trg_sie_cap_seed` — seed cap = 10
- `trg_sie_cap_lns` — L&S cap = 20
- `trg_current_state_cap_insert` / `trg_current_state_cap_update` — 280-char cap on `shells.current_state`

---

## The model

**A shell** is one row in the `shells` table plus rows it accumulates in
sibling tables (identity entries, decisions, archives, flags, projects,
skills). Its `system_prompt` carries the operating protocol; its identity
columns (`display_name`, `shortname`, `owner`, `role`, `mandate`) are
stable; its `current_state` is a 280-char rolling status; and its
`shell_memory_archives` rows are the per-session narrative log.

**The launcher** (`make launch` → `shell_core/scripts/run.py`):

1. Authenticates a user against `users` (scrypt-hashed password).
2. Picks a shell (interactively, or from CLI: `make launch-<shortname>`).
3. Composes a single flat `CLAUDE.md` from live DB state.
4. Opens a new row in `shell_memory_archives` (sets `shells.active_archive_id`).
5. Ensures the shell's per-shell Docker container (run-if-missing /
   start-if-stopped) and `docker exec`s `claude` into it. The shell's
   workdir is bind-mounted to `/workspace`, so the rendered `CLAUDE.md` is
   visible inside.

The composed `CLAUDE.md` *is* the session's memory budget at boot. Nothing
else is fetched. Subsequent reads (decision log, full skill content,
connections) happen on demand via SQL during the session.

**Forge** is a special shell — `shortname=forge`, `is_shared=1` — that
exists in every substrate from cold-boot. Its only purpose is to spawn new
shells. A user with zero owned shells lands in Forge automatically.

---

## How memory recall works

When `run.py` boots a shell, it queries the DB and writes a flat
`shells/<shortname>/CLAUDE.md`. Sources, in render order:

| Source | Rendered as |
|---|---|
| `~/.claude/CLAUDE.md` (harness-injected before everything) | universal preamble — LAWS, SYSTEM OVERRIDE, shell-selection logic |
| `shell_core/templates/boot.md` | per-substrate preamble (LAWS + SYSTEM OVERRIDE again, scoped) |
| Render fields (session_id, archive_id) | `## ACTIVE SESSION` |
| Authenticated user (`user_id`, `username`) | `## OPERATOR` — who is driving this session; Forge keys off this when assigning newly-created shells |
| `shells` identity columns (`display_name`, `shortname`, `owner`, `role`, `mandate`) | `## IDENTITY` |
| `shells.system_prompt` | `## SYSTEM PROMPT` (operating protocol — definitions, memory architecture, write protocol) |
| `shells.current_state` | `## CURRENT STATE` (rolling 280-char status) |
| `shell_identity_entries WHERE kind='seed'` | `## SEED` (row-per-entry, cap 10) |
| `shell_identity_entries WHERE kind='lns'` | `## LESSONS & STANCES` (row-per-entry, cap 20) |
| `projects` ⋈ `project_shells` | `## ACTIVE PROJECTS` |
| `skills` ⋈ `shell_skills` | `## SKILLS` (name + description only — content lazy-loaded on use) |
| `COUNT(*)` of seed / L&S / open flags | `## STATUS` |

The harness *also* injects a system-reminder each turn listing **plugin
skills** (auto-discovered from `~/.claude/plugins/`). That's a separate
live channel, not part of the rendered `CLAUDE.md`.

The lazy-loading principle: load the **map** at boot (skill names,
table names, where things live), fetch the **territory** on demand
(skill content, decision rationale, connections markdown). Keeps the
session-start budget flat and predictable.

---

## How memory writes work

Memory is written *as work happens*, not at session close. The shell's
`system_prompt` documents the per-table protocol; the short version:

| Surface | Write pattern |
|---|---|
| `shells.current_state` | `UPDATE` in place. 280-char trigger-enforced cap. Rolling status — never a log. |
| `shell_memory_archives.full_narrative` | One row per session, opened by `run.py` at boot. The shell appends `[HH:MM] {note}` lines at inflection points (decision, surprise, course change). |
| `shell_identity_entries` (seed) | `INSERT` only. Caps at 10, enforced by `trg_sie_cap_seed`. To curate, `UPDATE retired_at` (preserves the row). |
| `shell_identity_entries` (lns) | `INSERT` only. Caps at 20, enforced by `trg_sie_cap_lns`. Same retire-don't-edit pattern. |
| `shell_decisions` | `INSERT` only for major (M) decisions. Supersede via `parent_decision_id`. Never edit a prior row. |
| `flags` | `INSERT` to open, `UPDATE resolved=1` to close. ID convention: `<SHORT>-###`. |
| `shells.connections` | `UPDATE` free-form markdown when environment changes (new repo, moved path, deprecated service). Lazy-loaded on demand. |
| `projects` / `project_shells` | `INSERT` to add a project; `UPDATE projects.standing` when standing rules change. |

The cap triggers are load-bearing: they make "curate, don't accumulate"
mechanical. A shell trying to plant an 11th seed gets `RAISE(ABORT)` —
forcing an explicit retirement first.

---

## How shells get assigned

Two columns on `shells` decide visibility:

- `shells.user_id` — the owner. NULL for shared shells.
- `shells.is_shared` — `1` means the shell appears in every authenticated user's picker regardless of ownership.

The picker query (`run.py:list_shells`) is:

```sql
SELECT ... FROM shells
WHERE user_id = :me OR is_shared = 1
ORDER BY is_shared, shell_id
```

So a user always sees: their owned shells + every shared shell. Forge is
the only shared shell by convention; nothing in the schema prevents others.

**Assignment happens at creation.** When Forge runs the `create_shell`
skill, it reads the `## OPERATOR` block from its own rendered `CLAUDE.md`
(populated by `run.py` from the authenticated user) and INSERTs the new
shell row with `user_id = <operator>` and `is_shared = 0`. That makes the
new shell private to the user who created it — even though Forge itself is
shared.

This is the trick that makes one shared bootstrapper safe in a multi-user
substrate: Forge can be launched by anyone, but everything it spawns is
owned by whoever launched it.

---

## Creating new shells

From inside Forge:

1. The operator runs the `create_shell` skill.
2. Forge interviews: display_name, shortname, mandate, role, owner.
3. Forge INSERTs into `shells` (with `user_id` = the operator, `is_shared`
   = 0, `system_prompt` from a chosen template) and INSERTs links into
   `shell_skills` for any baseline skills.
4. Operator restarts (`make launch`) and picks the new shell.
5. The new shell runs `bootstrap_interview` on first boot — interviews the
   operator about projects, environment, and conventions, then writes a
   starter `current_state`, the first seed entry, and `connections`.

After bootstrap, the shell is fully self-managing: it writes its own
identity entries, opens flags, records decisions, appends to its session
narrative.

---

## The catalogue

A self-maintaining index of what exists in the substrate — routes,
routers, deps, libs, services, repos, notable files, automations, env
vars. The point: when a shell needs to find something, it should query
the catalogue instead of grepping the codebase. Every catalogued row
carries `(name, description_short)`, so the catalogue itself is small
enough to scan but information-dense enough to navigate from.

### Why

A shell booting cold into an unfamiliar substrate (or spawned via
`create_shell` for the first time) shouldn't have to read the whole
codebase to orient. Three rows in `dr_filepath` will point at the four
files that actually matter; one query against `dr_api` lists every
endpoint with its purpose. The catalogue is the index card; the code is
the territory.

### Architecture

```
typed registries (one row per thing, all carry name + description_short)
  dr_repo, dr_filepath, dr_router, dr_api, dr_lib,
  dr_dependencies, dr_services, dr_automations, dr_env
        │
        │  FK by (ref_table, ref_id)
        ▼
shell_dr_link  (per-shell binding, optional `role` column)
        │
        ▼
v_dr_catalogue       — substrate-wide projection
v_shell_catalogue    — per-shell, includes role annotation
```

Polymorphic association: `shell_dr_link.ref_table` ∈ {nine values}, with
`ref_id` pointing into the matching typed table. The two views UNION
across the typed tables and project to a uniform
`(ref_table, ref_id, name, description_short)` shape.

### The 9 surfaces

| Surface | What it lists | Source-of-truth |
|---|---|---|
| `dr_router` | FastAPI router files | First line of module docstring |
| `dr_api` | HTTP endpoints | `summary=` on each route decorator |
| `dr_dependencies` | npm + pip deps | `package.json` + `importlib.metadata` |
| `dr_lib` | Backend modules + UI lib files | Module docstring (Py) / first `//` comment (JS) |
| `dr_services` | pm2 long-running processes | `summary` field on each app in `ecosystem.config.cjs` |
| `dr_repo` | Tracked git repos | `gh repo view --json description` |
| `dr_filepath` | Notable paths in the substrate | Curated list in `dr_sync.py` |
| `dr_automations` | Scheduled / triggered jobs | Curated list in `dr_sync.py` |
| `dr_env` | Env vars the substrate uses | Curated list in `dr_sync.py` (no values stored) |

Six surfaces auto-derive from real state. Three are curated lists in
`dr_sync.py` itself — for content with no machine-readable source (e.g.,
"which paths are worth indexing"), the script *is* the source of truth.

### Sync triggers

- **FastAPI startup event** — every API restart calls `sync_all`,
  refreshing all 9 surfaces. Idempotent UPSERT (no duplicates). Failures
  log but don't block startup. This is the primary trigger because most
  populator sources require an API restart to take effect anyway.
- **`make db-sync`** — explicit on-demand refresh. Runs the same `sync_all`.
- **`python3 shell_core/scripts/dr_sync.py <target>`** — single-target
  refresh during debugging.

### Using it

```bash
# CLI surface
make catalogue                          # full listing (~111 rows)
make catalogue ARGS="flag"              # substring filter
make catalogue ARGS="--table dr_api"    # one ref_table only
make catalogue ARGS="--shell 1"         # per-shell view (with role column)
```

```sql
-- Direct SQL
SELECT * FROM v_dr_catalogue ORDER BY ref_table, name;
SELECT * FROM v_dr_catalogue WHERE ref_table = 'dr_api' AND name LIKE '%flag%';
SELECT * FROM v_shell_catalogue WHERE shell_id = 1;
```

### Adding new entries

| To add... | Edit... | Then... |
|---|---|---|
| A new HTTP route | Add `summary="..."` ≤100 chars to the decorator | API restart syncs |
| A new pm2 service | Add a `summary` field to its entry in `ecosystem.config.cjs` | `make db-sync` |
| A backend module | Add a module docstring (first line is the summary) | `make db-sync` |
| A UI lib file | Add a `// ...` comment as the first line | `make db-sync` |
| A notable filepath | Add to `_FILEPATH_ENTRIES` in `dr_sync.py` | `make db-sync` |
| A new automation | Add to `_AUTOMATION_ENTRIES` in `dr_sync.py` | `make db-sync` |
| A new env var | Add to `_ENV_ENTRIES` in `dr_sync.py` | `make db-sync` |

The discipline lives in two skills: `api-design` (route metadata) and
`catalogue_sync` (umbrella matrix covering all 9 surfaces, with the
pre-modify check pattern). `surface_catalogue` skill documents the
`make catalogue` usage.

---

## License

MIT — see [LICENSE](LICENSE).
