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

The substrate runs on a handful of host packages. `host-setup.sh` (phase 1
of `./install/setup.sh`) installs them; this is what each is for:

- **git**, **make** — clone the repo + Make entry points
- **Python 3.10+** — FastAPI runtime, launcher, admin scripts
- **Node 18+** + **npm** — SvelteKit UI
- **pm2** — host-side process manager for the UI, the browser-chat
  dispatcher, and the Ollama model-sync watcher (the API and broker run
  as their own containers)
- **Docker** + `docker-buildx`, `slirp4netns`, `fuse-overlayfs` — the
  per-shell container sandbox (run rootless, as the operator)
- **cronie** — runs the nightly `dr_*` catalogue sync

`claude` is **not** a host dependency — it is baked into the `dos-shell`
image and run via `docker exec` inside the container.

Installing the packages is only the start: the rootless-Docker
configuration — daemon under the operator's user systemd, the substrate
images, broker + API containers, pm2 supervisors, the catalogue cron —
is the scripted procedure in **[install/README.md](install/README.md)**.
The scripts are **Arch-only** (`pacman` gate); Ubuntu support would need
a parallel `host-setup-deb.sh` that doesn't ship yet.

> **Next:** the **[Quickstart](#quickstart)** below runs the install
> end-to-end; **[install/README.md](install/README.md)** has the per-phase
> detail; **[Cold bootstrap](#cold-bootstrap)** explains what the
> substrate build does.

---

## Quickstart

The full install is **one script** — `./install/setup.sh` — that runs nine
phases end-to-end. Two interactive moments, both up front (your `sudo`
password, then the first substrate user's username + password); everything
after runs unattended.

`setup.sh` is **Arch-only** (`pacman` gate). Ubuntu would need a parallel
`host-setup-deb.sh` that doesn't ship yet.

### Step 0 — sync, clone, .env (operator)

`host-setup.sh` (phase 1 of `setup.sh`) installs the system packages, so
you don't need to install them by hand — but on a rolling distro it is
worth syncing the package db first:

```bash
sudo pacman -Syu
```

If the kernel updates, reboot before continuing. Then clone the repo:

```bash
git clone https://github.com/jedbjorn/dos-arch.git ~/dos-arch
```

`setup.sh` refuses to start without the broker secrets file at
`~/.config/dos-arch/.env`. A script cannot author secrets — create it now:

```bash
cd ~/dos-arch
mkdir -p ~/.config/dos-arch
cp .env.example ~/.config/dos-arch/.env
nano ~/.config/dos-arch/.env
```

In `nano`: arrow keys move the cursor; type each value right after the `=`
sign (no spaces, no quotes); `Ctrl+O` then `Enter` to save, `Ctrl+X` to
exit. Two values are required (`ANTHROPIC_API_KEY` and `GITHUB_TOKEN`);
two more are optional, only needed if you want browser-chat to reach
non-Anthropic providers (`OPENAI_API_KEY`, `OLLAMA_CLOUD_API_KEY`).

**`ANTHROPIC_API_KEY`** *(required)* — create one in the Anthropic Console:
[console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys).
It looks like `sk-ant-…`:

```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
```

**`GITHUB_TOKEN`** *(required)* — a GitHub token the broker uses for git-over-HTTPS
(clone / pull / push) on behalf of shell containers. Two ways to get one:

- *Recommended — a fine-grained PAT.* Create one at
  [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new)
  (GitHub → Settings → Developer settings → Personal access tokens →
  Fine-grained tokens → Generate new token). Set:
  - **Repository access** → *Only select repositories* → just the repos
    your shells will work in. Narrow scope bounds the blast radius if the
    token is ever leaked.
  - **Repository permissions** → **Contents: Read and write** (*read* =
    clone/pull, *write* = push). **Metadata: Read-only** is selected
    automatically and is required. Leave everything else off.

  ```
  GITHUB_TOKEN=github_pat_xxxxxxxx
  ```

- *Quick — dev/test only.* If `gh` is already authenticated on the host,
  `gh auth token` prints a usable token — but it is **account-wide**, not
  scoped to specific repos. Wire it in directly:

  ```bash
  sed -i "s|^GITHUB_TOKEN=.*|GITHUB_TOKEN=$(gh auth token)|" ~/.config/dos-arch/.env
  ```

**`OPENAI_API_KEY`** *(optional)* — only needed if you want browser-chat to
reach GPT models. Create one at
[platform.openai.com/api-keys](https://platform.openai.com/api-keys); leave
the line blank to skip OpenAI entirely.

**`OLLAMA_CLOUD_API_KEY`** *(optional)* — only needed if you want
browser-chat to reach Ollama Cloud's hosted models (gpt-oss, deepseek,
kimi, qwen, glm, …). Create one at
[ollama.com/settings/keys](https://ollama.com/settings/keys); see the
**[Cloud models](#cloud-models-ollama-cloud)** section below for how to
populate and activate cloud rows.

### Run setup

```bash
./install/setup.sh
```

That's it. Nine phases run in order:

| # | What | Notes |
|---|---|---|
| 1 | `sudo ./install/host-setup.sh` | Asks for your sudo password. Packages, subuid/subgid, linger, cronie. |
| 2 | `make bootstrap`               | **Interactive** — prompts for the first substrate user's username + password. |
| 3 | `make install`                 | `.venv` + pip deps + `npm install`. |
| 4 | `./install/rootless-setup.sh`  | Fetches rootless-extras into `~/bin`, starts the rootless daemon, selects its CLI context. |
| 5 | `./install/build-image.sh`     | Builds `dos-shell`, `dos-broker`, `dos-api`. |
| 6 | `./install/broker-up.sh`       | `dos-net` network + `dos-broker` container. |
| 7 | `./install/api-up.sh`          | Migrate DB, host-side `dr_sync`, start `dos-api` on `127.0.0.1:8001`. |
| 8 | `make up`                      | pm2 starts `dosarch-ui` (5174), `dosarch-dispatch`, `dosarch-modelsync`. |
| 9 | `./install/cron-install.sh` + `make sync-models` | Daily catalogue cron; hardware probe + Ollama model read (non-fatal if Ollama absent). |

Each script is also runnable on its own — useful when fixing a partial
install. Full per-phase detail in
**[install/README.md](install/README.md#what-setupsh-runs)**.

**Pin a Claude Code version** into the `dos-shell` image:
`./install/setup.sh 2.1.133`. Default is `stable`.

### Then launch a shell

```bash
make launch
```

The launcher authenticates you, lists your shells (owned + shared), opens
or starts the picked shell's container, and `docker exec`s `claude` into
it. See **[Daily commands](#daily-commands)** below.

### Local models (Ollama)

dos-arch shells run against a local LLM served by Ollama on the host.
`setup.sh` does not install Ollama — pick the GPU variant by hand:

```bash
sudo pacman -S --needed ollama-cuda     # NVIDIA — offloads to the GPU
sudo pacman -S --needed ollama-rocm     # AMD
sudo pacman -S --needed ollama          # CPU-only
sudo systemctl enable --now ollama
```

Pull a model sized to your VRAM — see **[docs/model-tiers.md](docs/model-tiers.md)**
for picks per tier — then refresh the substrate's view:

```bash
ollama pull qwen2.5-coder:7b
make sync-models                  # read Ollama -> installed_models + models registry
```

`model_sync.py` is the source of truth for local models in the `models`
registry: it reads Ollama's installed set via `/api/tags` + `/api/show`,
UPSERTs each as a `provider='local'` row, classifies `supports_tools` +
`accepts_substrate_system` from the template, and flips inactive any row
whose model is no longer installed. No local rows are seeded at install
time — the registry starts empty for local models and `model_sync` fills
it from reality. The `dosarch-modelsync` pm2 process watches Ollama
continuously, so the registry tracks `ollama pull` / `ollama rm`
hands-free after the first sync.

Pick models the Ollama library tags as **"Tools"** — the browser-chat
dispatcher needs tool calls. Models without that capability still sync,
just registered as `status='inactive'`.

### Cloud models (Ollama Cloud)

dos-arch's browser-chat can also reach Ollama's hosted service — same
native `/api/chat` protocol as the local daemon, just with a bearer
token. Useful when you want a frontier-class model (gpt-oss:120b,
deepseek-v3.1:671b, kimi-k2, …) that won't fit in local VRAM.

Set `OLLAMA_CLOUD_API_KEY` in `~/.config/dos-arch/.env` (see Step 0),
then `pm2 restart dosarch-dispatch` so the dispatcher reloads it.

Populate the catalog from Ollama Cloud's public listing:

```bash
make sync-cloud-models            # anonymous /api/tags read — no key needed
```

That inserts one `provider='ollama_cloud'` row per cloud model, all
`status='inactive'` by default. To activate, open the **Ollama Cloud**
link in the UI's hamburger drawer (`/ollamacloudconfig`) — each row has a
single-click activate / deactivate toggle, and the page's **Refresh
catalog** button re-runs the sync without dropping to the shell.

Activated rows appear under **Ollama Cloud** in the chat sidebar's model
picker, alongside the local and Anthropic groups.

The down-sweep is conservative: a cloud row gets auto-deactivated only if
it was previously synced from `/api/tags` (`last_verified IS NOT NULL`)
and the latest catalog no longer lists it. Rows that were hand-inserted
or pre-date the sync stay put.

### Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `cannot read ~/.config/dos-arch/.env` (setup or broker) | Create the file: `mkdir -p ~/.config/dos-arch && cp .env.example ~/.config/dos-arch/.env`, then fill in the two keys. |
| `pacman: command not found` (host-setup) | Not an Arch-based host. `setup.sh` is Arch-only. |
| `failed retrieving file …` (host-setup) | Stale package database on a rolling distro — `sudo pacman -Syu` (reboot if the kernel updates), then re-run. |
| `XDG_RUNTIME_DIR unset` (rootless-setup) | Running in a detached session. Use a desktop terminal, a tty, or `ssh -t`. |
| `docker: command not found` (after install, new shell) | `~/bin` not on PATH — open a fresh shell, or `export PATH=$HOME/bin:$PATH`. |
| `connect: permission denied` on Docker socket | Wrong Docker context — `docker context use rootless`. |
| Daily `make launch` errors immediately | Check `pm2 ls` (the three `dosarch-*` apps), `docker ps` (`dos-api` + `dos-broker`), and `curl http://127.0.0.1:8001/health`. |

More cases — cgroup v2 delegation, user namespaces, etc. — in
**[install/README.md → Notes / troubleshooting](install/README.md#notes--troubleshooting)**.

### Updating procedure

Routine updates need no rebuild — the API and UI run from bind-mounted
source, so `git pull` + a restart picks up code changes. As the operator:

```bash
cd ~/dos-arch
git pull
./install/api-up.sh     # applies migrations, restarts dos-api
make restart            # bounces dosarch-ui, dosarch-dispatch, dosarch-modelsync
```

`api-up.sh` snapshots the DB automatically before migrating (see the path
it prints) — no manual backup is needed. `make db-backup` is there if you
want an extra one.

**Rebuild images** only when something under `docker/` changes, or to pin
a new Claude Code version:

```bash
./install/build-image.sh         # rolls history-1..3, builds fresh :latest
./install/broker-up.sh           # recreate dos-broker on the new image
./install/api-up.sh              # recreate dos-api on the new image
```

Existing per-shell containers keep running the old `dos-shell` image until
recreated.

### Teardown procedure

`./install/teardown.sh` is the inverse of the install. Run as the operator:

```bash
cd ~/dos-arch
./install/teardown.sh
```

Five operator-side phases: pm2 delete the three `dosarch-*` apps; remove
all containers; prune images/networks/volumes/build cache; uninstall
rootless Docker; wipe `~/.local/share/docker`.

**What it leaves alone — by design, so a re-`setup.sh` rebuilds without
re-asking:** pacman packages, the operator's subuid/subgid + linger, the
repo clone, `~/.config/dos-arch/.env`, `~/db_backups/dos-arch`, and the
`dr_sync` cron line. To rebuild from here, re-run `./install/setup.sh`.

#### Complete rip-out

For a full uninstall:

```bash
crontab -l | grep -v dr-sync-cron | crontab -        # remove the cron line
rm -rf ~/.config/dos-arch                            # broker secrets (had real keys)
rm -rf ~/db_backups/dos-arch                         # DB snapshots
rm -rf ~/dos-arch                                    # the clone
sudo loginctl disable-linger $(id -un)               # only if no other rootless service uses it
sudo sed -i "/^$(id -un):/d" /etc/subuid /etc/subgid # only if no other rootless service needs the range
```

Optional — remove the packages (`pacman -Rns` refuses if anything still
depends on them):

```bash
sudo pacman -Rns docker docker-buildx slirp4netns fuse-overlayfs cronie
```

`.env` carried real credentials — if the host is shared or untrusted,
rotate them after deletion. `rm` clears them from disk, not from anywhere
they were already used.

#### Fresh-DB rebuild

To reset every build artifact (DB, `.venv`, `node_modules`, rendered
shells) but keep the host setup, from the repo root:

```bash
git clean -xfd
./install/setup.sh
```

`git clean -xfd` removes everything git ignores — no path list to keep in
sync. `.env` lives at `~/.config/dos-arch/.env` outside the clone, so it
survives.

---

## Daily commands

All run as the operator, from anywhere in `~/dos-arch`:

```bash
cd ~/dos-arch

make launch                       # picker: auth, pick a shell, launch it in its container
make launch-<shortname>           # boot that shell directly (skip picker)
make create-user                  # provision a new substrate user
make set-password                 # reset a user's launcher password
make gen-api-key ARGS=<shortname> # issue/rotate a shell's substrate-API key
make up                           # pm2 start the UI + dispatcher + modelsync
make down                         # pm2 delete the same three
make restart                      # bounce them
make status                       # pm2 ls
make logs                         # pm2 logs (Ctrl-C to detach)
make health                       # GET http://127.0.0.1:8001/health
make dispatch                     # run the browser-chat dispatcher in the foreground (debug)
make db-backup                    # snapshot shell_db.db -> ~/db_backups/dos-arch/<ts>.db
make migrate ARGS=--status        # preview pending DB migrations
make migrate                      # apply them
make catalogue ARGS='flag'        # print the catalogue (substring filter)
make sync-models                  # re-read Ollama into the registry
```

The `dos-api` + `dos-broker` containers stay up between sessions; only
per-shell containers spin up at `make launch` and stay running across
re-launches of the same shell.

The launcher runs as you, the operator — no `sudo`, no session hop.
Convenience alias if you want to launch from any directory:

**fish:**
```fish
function dosarch
    cd ~/dos-arch && make launch
end
funcsave dosarch
```

**bash:**
```bash
echo 'dosarch() { (cd ~/dos-arch && make launch); }' >> ~/.bashrc
source ~/.bashrc
```

---

## Cold bootstrap

The Quickstart is the command sequence; this is the explanation behind
phase 2 — what `make bootstrap` does, and why the substrate ends up
self-healing.

`make bootstrap` runs `shell_core/scripts/bootstrap.py`, which:
1. Errors out if `shell_db.db` already exists (use `make db-backup` first if recreating).
2. Executes `schema.sql` against a new SQLite file, then stamps every shipped migration as applied.
3. Seeds every skill from `shell_core/assets/skills/` — one tracked `.md` per skill, frontmatter → columns, body → `content`.
4. Seeds the remote model registry (Anthropic + OpenAI). Local models are not seeded — they appear when `model_sync.py` reads Ollama (Quickstart phase 9 + the `dosarch-modelsync` pm2 watcher).
5. Seeds Forge, the shared bootstrap shell, from `shell_core/assets/shells/forge.md` (`is_shared=1`, `create_shell` attached).
6. Prompts for the first user — username + password. This is the substrate admin.
7. Seeds Sys-Admin, the resident admin/dev shell, owned by that user — identity from `shell_core/assets/shells/sys-admin.md`, with every `common`-flagged skill attached, `is_admin=1`, `browser_chat=1`.
8. Seeds every tool from `shell_core/assets/tools/` and scopes each handler family to its skill via `[skill_map]`.

So a freshly-bootstrapped substrate already has a working admin shell. On
`make launch` the first user enters their username, clears the password
challenge, and picks Sys-Admin — or Forge, to spawn more shells.

`api-up.sh` (Quickstart phase 7) bind-mounts `shell_core/` into the
`dos-api` container and publishes the API on `127.0.0.1:8001`, so a later
`git pull` plus a re-run picks up code changes with no image rebuild — see
**[Updating procedure](#updating-procedure)**.

**The launcher self-heals.** On every `make launch`, `run.py` calls
`ensure_forge(conn)`. If the Forge row is missing — accidentally deleted,
clone restored from backup, partial DB — it's re-seeded transparently
before auth runs. So Forge is always present at boot. Only a missing DB
file requires `make bootstrap`.

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
  api/                    FastAPI substrate — routers (shells, users, skills, flags, catalogue, admin) + services (boot_document, …)
  ui/                     SvelteKit substrate UI (routes: /shells, /flags, /plans; floating browser-chat panel with model-switch dropdown)
  broker/                 Credential broker — egress proxy; injects auth so shell containers run credential-free
  schema.sql              Canonical SQLite schema (~34 tables + triggers + 2 catalogue views)
  shell_db.db             Local SQLite store — gitignored, built via `make bootstrap`
  shell_db.py             Connection helper used by api/common/db.py
  scripts/run.py          Launcher: auth → picker → render CLAUDE.md → docker exec claude
  scripts/bootstrap.py    One-shot bootstrapper — `make bootstrap`
  scripts/db_init.py      Seeding library — seed_skills / ensure_forge / seed_sys_admin
  scripts/dr_sync.py      Catalogue populator — wired sync targets + dispatch
  services/dispatch_live.py  Browser-chat dispatcher — the own-runtime agent loop (`make dispatch`)
  services/providers/     ProviderAdapter seam — the model-agnostic boundary (Anthropic + OpenAI adapters)
  scripts/catalogue.py    `make catalogue` — print the catalogue grouped by ref_table
  scripts/create_user.py / set_password.py  Admin scripts for users
  assets/                 Seed data — skills/*.md + shells/{forge,sys-admin}.md
  templates/              catalog_universal.md — baked universal layer of the boot-prompt catalog
  migrations/             Versioned *.sql migrations — applied in order by migrate.py (auto-run in api-up.sh; on demand via make migrate). schema.sql builds a fresh DB; migrations carry an existing one forward. _legacy/ holds pre-runner .py migrations, not applied.
docker/
  shell/                  Dockerfile for the dos-shell image — one container per shell instance
  broker/                 Dockerfile for the dos-broker image — the credential broker
  api/                    Dockerfile for the dos-api image — the substrate memory API
install/                  Rootless-Docker host bootstrap — host-setup / rootless-setup / build-image / broker-up / api-up / cron-install / teardown (see install/README.md)
docs/                     specs/ (agnostic-runtime, memory-recall) + model-tiers.md; archive/ holds the superseded harness-spec
shells/<shortname>/       Per-shell working dirs (managed by run.py; CLAUDE.md regenerated each session; bind-mounted into the shell's container as /workspace)
.env.example              Template for .env — broker secrets (ANTHROPIC_API_KEY, GITHUB_TOKEN); .env is gitignored
ecosystem.config.cjs      pm2 process map (UI on 5173; API + broker run as containers)
Makefile                  Entry points: install, bootstrap, db-sync, db-backup, catalogue, launch, dispatch, up/down/health
```

---

## What's in the database

`shell_core/shell_db.db` is local-only (not in git). `shell_core/schema.sql`
is the canonical schema. Tables, grouped by purpose:

**Identity**
- `users` — username, scrypt password hash + salt, theme prefs.
- `shells` — one row per shell. Identity columns + `boot_document` (materialized boot doc) + `current_state` + `connections` + `is_shared` + `user_id` (owner) + `browser_chat` (1 = served by the dispatcher).
- `shell_identity_entries` — seed and L&S entries, one row each. Caps enforced by triggers.
- `shell_decisions` — major decisions log. Append-only; supersede via `parent_decision_id`.

**Sessions & narrative**
- `shell_memory_archives` — one row per session. `full_narrative` accumulates throughout.
- `chat_sessions` / `chat_messages` — browser-chat conversations and their messages — the dispatcher's conversation store (separate from the per-shell `make launch` session log).

**Skills**
- `skills` — skill definitions: `name`, `description`, `category`, `content`. The content is the full procedure body, lazy-loaded.
- `shell_skills` — many-to-many: which skills are attached to which shell. Drives the `## SKILLS` block at boot.

**Tools & models** (agnostic-runtime registry)
- `tools` — provider-agnostic tool registry: `name`, `description`, `kind`, `spec` (JSON parameter schema), `handler`, `skill_id`. A tool is *general* (`skill_id` NULL — every shell gets it, e.g. the substrate `api_*` verbs) or *skill-bound* (`skill_id` set — rendered and callable only for shells granted that skill). The dispatcher loads tool definitions from here, not a hard-coded list.
- `models` — every model the system *can* use: `provider`, `tool_dialect`, `endpoint`, `auth_ref`, plus cost and limit columns. The model-switch dropdown reads `status='active'` rows; `chat_sessions.model_id` points a conversation at one. Distinct from `installed_models` (the per-host Ollama install inventory).

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
repos, files, automations, env vars). Refreshed by a daily cron and on
every API restart. Each row
carries `name` + `description_short` (≤100 chars) for fast lookup. See the
**The catalogue** section below for the full architecture.

Triggers worth knowing about:
- `trg_sie_cap_seed` — seed cap = 10
- `trg_sie_cap_lns` — L&S cap = 20
- `trg_skills_explicit_default` — defaults a skill's `--name` trigger token on insert

Entry-body and `current_state` *lengths* are soft targets, not triggers —
the renderer states the aim, an occasional overrun is accepted (migration
020). Only the seed / L&S *count* caps stay trigger-enforced.

---

## The model

**A shell** is one row in the `shells` table plus rows it accumulates in
sibling tables (identity entries, decisions, archives, flags, projects,
skills). Its identity columns (`display_name`, `shortname`, `owner`, `role`,
`mandate`) and `connections` are stable; its `current_state` is a rolling
now/next status; and its `shell_memory_archives` rows are the per-session
narrative log.

**The launcher** (`make launch` → `shell_core/scripts/run.py`):

1. Authenticates a user against `users` (scrypt-hashed password).
2. Picks a shell (interactively, or from CLI: `make launch-<shortname>`).
3. Composes `CLAUDE.md` — the typed section catalog — from live DB state.
4. Opens a new row in `shell_memory_archives` (sets `shells.active_archive_id`).
5. Ensures the shell's per-shell Docker container (run-if-missing /
   start-if-stopped) and `docker exec`s `claude` into it. The shell's
   workdir is bind-mounted to `/workspace`, so the rendered `CLAUDE.md` is
   visible inside.

The composed `CLAUDE.md` *is* the session's memory budget at boot. Nothing
else is fetched. Subsequent reads (decision log, full skill content,
connections) happen on demand via SQL during the session.

**The dispatcher** (`make dispatch` → `shell_core/services/dispatch_live.py`)
is a second runtime. Where the launcher `docker exec`s the Claude Code CLI
into a container, the dispatcher *is* the harness: it polls `chat_messages`
for inbound browser-chat messages, runs the model loop itself — every model
call through a `ProviderAdapter` (`shell_core/services/providers/`) — with
`api_*` tools, and writes the reply back. A shell opts in with
`browser_chat = 1`. Its context is the materialized **boot document**
(`shells.boot_document`), fetched via `GET /shells/{id}/session-start` — the
dispatcher's equivalent of the launcher's rendered `CLAUDE.md`. The model is
resolved per turn from the `models` registry — a conversation's
`chat_sessions.model_id` selects it; the Anthropic and OpenAI adapters ship
today, the Ollama (local) adapter is next. Alpha constraints: it calls the
substrate API unauthenticated over localhost — so
it needs `ANTHROPIC_API_KEY` in its environment and must not be reached from
off the host. The `make launch` CLI path and the dispatcher coexist.

**Forge** is a special shell — `shortname=forge`, `is_shared=1` — that
exists in every substrate from cold-boot. Its only purpose is to spawn new
shells. A user with zero owned shells lands in Forge automatically.

---

## How memory recall works

When `run.py` boots a shell it queries the DB and writes
`shells/<shortname>/CLAUDE.md` — the **typed section catalog**, the
16-section document both render paths compose through
`shell_render.assemble_catalog`. One shared composer; the launcher writes
it to a file, the dispatcher materializes it to a column.

A **baked universal layer** (`templates/catalog_universal.md`) supplies the
sections identical for every shell; the rest render from live DB state.
In catalog order:

| Section | Source |
|---|---|
| `## SYSTEM OVERRIDE ##` (preamble) | baked — `catalog_universal.md` |
| `## BOOT ##` | runtime — wall-clock, session / archive ids, operator |
| `## IDENTITY ##` | `shells` identity columns + `users` |
| `## DEFINITIONS ##` | baked — `catalog_universal.md` |
| `## OPERATING CONTEXT ##` | `shells.connections` |
| `## ACTIVE PROJECTS ##` | `projects` ⋈ `project_shells` |
| `## TOOLS ##` | static common-tool roster, shaped by the model's dialect |
| `## SKILLS AVAILABLE ##` | `skills` ⋈ `shell_skills` — name + triggers (content lazy-loaded) |
| `## MEMORY PROTOCOL ##` | baked — `catalog_universal.md` |
| `## CURRENT STATE ##` | `shells.current_state` |
| `## SEED ##` | `shell_identity_entries WHERE kind='seed'` (cap 10) |
| `## LESSONS & STANCES ##` | `shell_identity_entries WHERE kind='lns'` (cap 20) |
| `## RECENT DECISIONS ##` | `shell_decisions` — most recent few |
| `## OPEN FLAGS ##` | `COUNT(*)` of open flags — a pointer, not the flags |
| `## LAWS ##` | baked — `catalog_universal.md` |
| `## COMMUNICATION ##` | baked — `catalog_universal.md` |
| `## OUTPUT SHAPE ##` | universal, shaped by the model's dialect |

The harness *also* injects its own `~/.claude/CLAUDE.md` and a
system-reminder each turn listing **plugin skills** (auto-discovered from
`~/.claude/plugins/`). That is a separate live channel, not part of the
rendered catalog.

The lazy-loading principle: load the **map** at boot (skill names + their
triggers, section pointers, where things live), fetch the **territory** on
demand (skill content, decision rationale, connections markdown). Keeps the
session-start budget flat and predictable.

The browser-chat dispatcher composes the *same* catalog by a different
route: `compose_boot_document()` calls `assemble_catalog` and stores the
result in `shells.boot_document`, a **materialized** column kept fresh by
the API's identity-write paths (re-render on write, no DB triggers) and
re-materialized on a model switch — so its dialect-shaped Tools and Output
sections match the conversation's model. `GET /shells/{id}/session-start`
returns that column plus a small live tail (datetime, open-flag count,
unread inbox); the dispatcher delivers the column as a cached system block
and the tail as a fresh one each turn.

---

## How memory writes work

Memory is written *as work happens*, not at session close. The short version:

| Surface | Write pattern |
|---|---|
| `shells.current_state` | `UPDATE` in place. Rolling now/next status, never a log — aim ~500 chars (a soft target, not enforced). |
| `shell_memory_archives.full_narrative` | One row per session, opened by `run.py` at boot. The shell appends `[HH:MM] {note}` lines at inflection points (decision, surprise, course change). |
| `shell_identity_entries` (seed) | `INSERT` only. Caps at 10, enforced by `trg_sie_cap_seed`. To curate, `UPDATE retired_at` (preserves the row). |
| `shell_identity_entries` (lns) | `INSERT` only. Caps at 20, enforced by `trg_sie_cap_lns`. Same retire-don't-edit pattern. |
| `shell_decisions` | `INSERT` only for major (M) decisions. Supersede via `parent_decision_id`. Never edit a prior row. |
| `flags` | `INSERT` to open, `UPDATE resolved=1` to close. ID convention: `<SHORT>-###`. |
| `shells.connections` | `UPDATE` free-form markdown when environment changes (new repo, moved path, deprecated service). Lazy-loaded on demand. |
| `projects` / `project_shells` | `INSERT` to add a project; `UPDATE projects.standing` when standing rules change. |

The seed and L&S **count** caps are load-bearing: they make "curate, don't
accumulate" mechanical. A shell trying to plant an 11th seed gets
`RAISE(ABORT)` — forcing an explicit retirement first. Entry *length* is a
soft target, not a trigger (migration 020).

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
skill, it reads the `operator:` line from the `## BOOT ##` section of its
own rendered `CLAUDE.md` (populated by `run.py` from the authenticated
user) and INSERTs the new
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
   = 0, and `role` / `mandate` / `connections` from the interview) and
   INSERTs links into `shell_skills` for any baseline skills.
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

- **Daily cron** — `cron-install.sh` (Quickstart step 11) installs a
  04:00 host-side `make db-sync`. This is the only *automatic full* (9/9
  surface) sync, and the primary one — it runs host-side with `git`, Node,
  and the whole repo in reach. Each run records a row in `dr_sync_runs`
  (`trigger_kind='cron'`); a stale newest `run_at` means the cron stopped.
- **FastAPI startup event** — every API restart runs `sync_all`. But the
  `dos-api` container can't reach `git` or `ecosystem.config.cjs`, so it
  no-ops `dr_repo` + `dr_services` — 7 of the 9 surfaces refresh.
  Idempotent UPSERT; failures log but don't block startup.
- **`make db-sync`** — explicit on-demand full refresh, host-side (the
  cron command, minus the schedule). Run it after a change you don't want
  to wait until 04:00 to pick up.
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
