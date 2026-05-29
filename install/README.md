# Host bootstrap — rootless Docker substrate (Arch)

Reproducible setup of the dos-arch substrate on a fresh Arch-based host
(Arch, CachyOS, EndeavourOS, Manjaro, …). Takes a clean system to:

- the operator running **rootless Docker** — no service user, zero sudo on
  the daily path
- the **`dos-broker:latest`** credential-broker image, built (the only
  container image — dos-arch is an API system, so the API runs on the host,
  not in a container, and there are no per-shell containers)
- the **`dos-broker`** container running on the **`dos-net`** network
- **pm2** supervising the substrate **API** (uvicorn on `127.0.0.1:8001`),
  the SvelteKit UI, the browser-chat dispatcher, and the Ollama model-sync
  watcher
- a **04:00 daily cron** refreshing the `dr_*` catalogue

Tested on CachyOS, kernel 7.0, Docker 29.4.3, x86_64.

## Single-user model

The substrate, rootless Docker, every container, every pm2 process — all run
as the **operator** (your normal login). There is no dedicated service user,
no `machinectl` hop, no ACL plumbing. The only step that needs root is
`host-setup.sh`, which installs system packages and adds the operator's
subuid/subgid range; everything after runs unattended as the operator.

## Prerequisites

- An Arch-based host with `pacman`, `systemd`, `acl`, and kernel ≥ 5.13
  (native rootless overlayfs; older kernels fall back to `fuse-overlayfs`).
- `sudo` access for the operator.
- This repository cloned to a path the operator owns (this doc assumes
  `~/dos-arch`).
- A real login session — desktop terminal, tty, or `ssh -t`.
  `rootless-setup.sh` needs a user systemd manager + `XDG_RUNTIME_DIR`,
  which a detached SSH session without `-t` doesn't provide.

## Install

The canonical path is one script:

```bash
cd ~/dos-arch
./install/setup.sh
```

Before running it, **create the broker secrets file**. A script cannot
author secrets; `setup.sh` refuses to start without one:

```bash
mkdir -p ~/.config/dos-arch
cp .env.example ~/.config/dos-arch/.env
nano ~/.config/dos-arch/.env       # fill in ANTHROPIC_API_KEY + GITHUB_TOKEN
```

The two secrets — what they are, where to get them, what scope to grant —
are detailed in the main [README](../README.md#step-0--dependencies--env-operator).

Two interactive moments, both up front:

- **`sudo` password prompt** during `host-setup.sh` (step 1) — your password.
- **First substrate user** during `make bootstrap` (step 2) — pick a username
  and password. That user becomes the substrate admin and owns the resident
  Sys-Admin shell.

Everything after runs unattended. Idempotent — safe to re-run.

## What setup.sh runs

Eight phases. Each one is also runnable on its own — useful when fixing a
partial install or rebuilding one component.

| # | Script / target               | What it does |
|---|--------------------------------|---|
| 1 | `sudo ./install/host-setup.sh` | pacman: `git base-devel python nodejs npm cronie docker docker-buildx slirp4netns fuse-overlayfs`; npm -g pm2 (if missing); enable cronie; add the operator's subuid/subgid range; enable-linger so the user systemd manager (and rootless Docker) survive logout; if `ollama.service` is present, write the dos-arch tuning drop-in (flash attention + q8_0 KV cache). |
| 2 | `make bootstrap`               | Apply `schema.sql`, seed skills + tools + remote models, seed Forge, prompt for the first user (username + password), seed Sys-Admin owned by that user. |
| 3 | `make install`                 | Create `.venv` with pip deps (`fastapi uvicorn pydantic anthropic openai httpx psutil`); `npm install` in `shell_core/ui`. |
| 4 | `./install/rootless-setup.sh`  | Fetch version-matched rootless-extras into `~/bin`, run `dockerd-rootless-setuptool.sh install`, `systemctl --user enable --now docker.service`, `docker context use rootless`, verify with `docker run hello-world`. |
| 5 | `./install/build-image.sh`     | Build the `dos-broker` image (the only container image). Rolling history-1..3 (no manual pruning); old `:latest` rotates to `:history-1`, etc. |
| 6 | `./install/broker-up.sh`       | Create the `dos-net` network, run `dos-broker` with `--env-file ~/.config/dos-arch/.env`, health-check it. |
| 7 | `make migrate` + `make up`     | Apply pending DB migrations, then pm2 starts four host apps: `dosarch-api` (uvicorn on `127.0.0.1:8001`), `dosarch-ui` (SvelteKit on `127.0.0.1:5174`), `dosarch-dispatch` (browser-chat dispatcher), `dosarch-modelsync` (Ollama watcher). The API runs its catalogue + model-sync at startup. |
| 8 | `./install/cron-install.sh` + `make sync-models` | Install the 04:00 daily `dr_*` catalogue sync cron (idempotent — keyed by a marker comment); `collect_hardware` probes this host into `user_hardware`, then `model_sync` reads Ollama's installed set into `installed_models` and promotes each into the `models` registry. If Ollama is absent, the hardware probe still lands and the model read is skipped non-fatally. |

All idempotent.

## Verify

```bash
docker ps                                            # dos-broker up (the only container)
pm2 ls                                               # four dosarch-* apps online
curl -fsS http://127.0.0.1:8001/health               # {"status":"ok"}
crontab -l | grep dr-sync-cron                       # the catalogue cron
sqlite3 shell_core/shell_db.db \
  "SELECT shortname FROM shells;"                    # forge, sysadmin
```

## Local models (Ollama)

dos-arch shells run against a local LLM served by **[Ollama](https://ollama.com)**
on the host. Ollama runs outside the rootless-Docker sandbox; the substrate
reaches it over the host loopback.

`setup.sh` does **not** install Ollama — pick the GPU variant by hand:

```bash
sudo pacman -S --needed ollama-cuda     # NVIDIA
sudo pacman -S --needed ollama-rocm     # AMD
sudo pacman -S --needed ollama          # CPU-only
sudo systemctl enable --now ollama
sudo ./install/ollama-tune.sh           # flash attention + q8_0 KV cache
```

`ollama-tune.sh` writes `/etc/systemd/system/ollama.service.d/dos-arch.conf`
with `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0` — typically
10–30% faster prefill+decode and half the KV memory at near-zero quality
cost. If Ollama was already installed when you ran `setup.sh`, this drop-in
is already in place; if you install Ollama later, run it by hand.

Verify with `ollama --version` and, if a GPU is expected, `nvidia-smi`.

Pull a model sized to your VRAM — see
**[docs/model-tiers.md](../docs/model-tiers.md)** for picks per tier
(8 / 12 / 24 / 32 / 48 / 128 GB):

```bash
ollama pull qwen2.5-coder:7b
```

Smoke-test that the GPU is doing the work:

```bash
ollama run qwen2.5-coder:7b "write a one-line shell function" --verbose
ollama ps
```

`--verbose` prints `eval rate` (tokens/s) — tens of tok/s for a GPU-resident
7B, single digits if it fell back to CPU. `ollama ps`'s `PROCESSOR` column
should be `100% GPU`; `CPU` or a split means the model spilled out of VRAM.

Then refresh the substrate's view:

```bash
make sync-models
```

```sql
SELECT hostname, gpu, vram_gb, vram_tier FROM user_hardware;
SELECT name, provider, params, size_gb, min_vram_gb, status FROM installed_models;
SELECT name, provider, status, supports_tools FROM models WHERE provider='local';
```

The `dosarch-modelsync` pm2 process watches Ollama continuously, so the
registry tracks `ollama pull` / `ollama rm` hands-free after the first sync.
No local rows are seeded at install time — the registry starts empty for
local models and `model_sync` fills it from reality.

## Updating

Routine updates need no rebuild — the API, UI and dispatcher all run from
the source tree, so `git pull` + migrate + restart picks up code changes:

```bash
cd ~/dos-arch
git pull
make db-backup          # migrate.py also snapshots, but an extra one is cheap
make migrate            # apply any pending migrations BEFORE bouncing services
make restart            # bounces dosarch-api, dosarch-ui, dosarch-dispatch, dosarch-modelsync
```

Order matters: migrate before restart, so the services don't open a DB whose
schema a migration is about to change (see CC-071). The API reapplies its
catalogue + model-sync on restart.

**Rebuild the image** only when something under `docker/broker/` (or the
broker source) changes:

```bash
./install/build-image.sh         # rolls history-1..3 and builds fresh dos-broker:latest
./install/broker-up.sh           # recreate dos-broker on the new image
```

## Teardown

`./install/teardown.sh` is the inverse of the install. Run as the operator:

```bash
cd ~/dos-arch
./install/teardown.sh
```

Five operator-side phases:

1. pm2 delete the four `dosarch-*` apps.
2. Remove all containers (`docker rm -f`).
3. Prune images, networks, volumes, build cache (`docker system prune -af --volumes`).
4. Uninstall rootless Docker (`dockerd-rootless-setuptool.sh uninstall`,
   user systemd unit stop).
5. Wipe the rootless Docker data directory (`~/.local/share/docker`).

**What teardown.sh leaves alone — by design, so a re-`setup.sh` rebuilds
without re-asking:**

- pacman packages
- the operator's subuid/subgid + linger
- the repo clone
- `~/.config/dos-arch/.env` (broker secrets)
- `~/db_backups/dos-arch` (DB snapshots)
- the `dr_sync` cron line in the operator's crontab

To rebuild from here, stop — the host is clean — and re-run
`./install/setup.sh`.

### Complete rip-out

For a full uninstall, also remove these — as the operator:

```bash
crontab -l | grep -v dr-sync-cron | crontab -        # remove the cron line
rm -rf ~/.config/dos-arch                            # broker secrets (had real keys)
rm -rf ~/db_backups/dos-arch                         # DB snapshots
rm -rf ~/dos-arch                                    # the clone
sudo loginctl disable-linger $(id -un)               # only if no other rootless service uses it
sudo sed -i "/^$(id -un):/d" /etc/subuid /etc/subgid # only if no other rootless service needs the range
```

Optional — remove the packages. `pacman` refuses if a package still has
dependents (on CachyOS, `fuse-overlayfs` is commonly required by
`profile-sync-daemon`) — drop any such package from the list, or skip this
step entirely: the packages are inert once Docker is uninstalled.

```bash
sudo pacman -Rns docker docker-buildx slirp4netns fuse-overlayfs cronie
```

`.env` carried real credentials (`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`) — if
the host is shared or untrusted, rotate them after deletion. `rm` clears
them from disk, not from anywhere they were already used.

### Fresh-DB rebuild

To keep the host setup but reset every build artifact (DB, `.venv`,
`node_modules`, `.svelte-kit`, rendered shells), from the repo root:

```bash
git clean -xfd
./install/setup.sh
```

`git clean -xfd` removes everything git ignores — no path list to keep in
sync. `.env` lives at `~/.config/dos-arch/.env` outside the clone, so it
survives.

## Scripts reference

| Script | Runs as | Does |
|---|---|---|
| `host-setup.sh`     | operator (sudo) | Packages, subuid/subgid, linger, cronie; calls `ollama-tune.sh` if Ollama is installed. The only step needing root. |
| `ollama-tune.sh`    | operator (sudo) | Systemd drop-in for `ollama.service` — flash attention + q8_0 KV cache. Run by hand after a late Ollama install. |
| `rootless-setup.sh` | operator        | Install + start rootless Docker. |
| `build-image.sh`    | operator        | Build `dos-broker` (the only container image; rolling history). |
| `broker-up.sh`      | operator        | `dos-net` network + `dos-broker` container. |
| `cron-install.sh`   | operator        | Daily `dr_*` catalogue sync cron (`04:00`, idempotent). |
| `setup.sh`          | operator        | One-command install — runs all of the above in the right order. |
| `teardown.sh`       | operator        | Reverse of install (operator-side; leaves packages + secrets in place). |

All idempotent — safe to re-run.

## Notes / troubleshooting

| Symptom | Cause → fix |
|---|---|
| `pacman: command not found` (host-setup) | Not an Arch-based host. setup.sh is Arch-only; Ubuntu would need a parallel `host-setup-deb.sh` that doesn't exist yet. |
| `XDG_RUNTIME_DIR unset` (rootless-setup) | Running in a detached session. Use a desktop terminal, a tty, or `ssh -t`. |
| `cannot read ~/.config/dos-arch/.env` (setup / broker) | Create it: `mkdir -p ~/.config/dos-arch && cp .env.example ~/.config/dos-arch/.env`, fill in the two keys. |
| `docker: command not found` (after install, new shell) | rootless-setup writes `~/bin` to your PATH via the setuptool; open a new shell, or `export PATH=$HOME/bin:$PATH`. |
| `dockerd-rootless-setuptool.sh` warns about cgroup v2 delegation | Create `/etc/systemd/system/user@.service.d/delegate.conf` with `[Service]\nDelegate=cpu cpuset io memory pids`, then `sudo systemctl daemon-reload` and re-run `rootless-setup.sh`. |
| `unprivileged user namespaces are disabled` | `sudo sysctl -w kernel.unprivileged_userns_clone=1` (persist in `/etc/sysctl.d/`). Arch defaults to enabled. |
| `broker-up.sh` says `connect: permission denied` on Docker | Wrong Docker context — `docker context use rootless`. |
| `pacman -S` reports `failed retrieving file …` | Stale package database on a rolling distro — `sudo pacman -Syu` (reboot if the kernel updates), then re-run. |
| **Why a single-user model** | Earlier iterations ran rootless Docker under a dedicated `dos-arch` service user; the operational cost of the `machinectl` hop and ACL plumbing on the operator's clone outweighed the sandbox benefit on a single-user host. The OS-level sandbox boundary is now rootless Docker itself, run by the operator. |
| **The `docker` package has no rootless scripts** | Arch/CachyOS package `dockerd`/`containerd` but not `dockerd-rootless*.sh`. `rootless-setup.sh` fetches the version-matched scripts + `rootlesskit` from `download.docker.com`; `dockerd`/`containerd` stay pacman-managed and auto-update via `pacman -Syu`. |
