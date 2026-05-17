# Host bootstrap — rootless Docker substrate (Arch)

Reproducible setup of the dockerized substrate on a fresh Arch-based host
(Arch, CachyOS, EndeavourOS, …). Takes a clean system to:

- an unprivileged **`dos-arch`** service user running **rootless Docker** —
  zero sudo on the daily launch path
- the **`dos-shell:latest`** shell-instance, **`dos-broker:latest`**
  credential-broker, and **`dos-api:latest`** substrate-API images, built
- the **`dos-broker`** container running on the **`dos-net`** network

Tested on CachyOS, kernel 7.0, Docker 29.4.3, x86_64.

## The two users

Setup runs across **two separate Linux accounts** on the host. Knowing which
one you are in at any moment is the single most important thing here — most
install mistakes are a command run as the wrong user.

| User | What it is | Runs |
|---|---|---|
| **operator** — your normal login (e.g. `j3d1`) | The human account that owns the repo clone. | `sudo` steps, `setfacl`, editing `.env` — anything needing your files or root. |
| **`dos-arch`** | Unprivileged service user, created by `host-setup.sh`. Owns rootless Docker. | Every `rootless-setup.sh` / `build-image.sh` / `broker-up.sh` / `docker` command. |

Tell them apart by the **shell prompt**: `[dos-arch@host …]$` means you are the
service user; anything else (e.g. `[USERNAME@host …]$`) means you are the operator.

Enter a `dos-arch` shell with `sudo machinectl shell dos-arch@` (run as the
operator); leave it with `exit`.

> **`dos-arch` is passwordless and not a sudoer.** Never run `sudo` inside a
> `dos-arch` session — it prompts for a password that does not exist and
> dead-ends. In particular, do **not** re-run `sudo machinectl shell dos-arch@`
> when you are already in a `dos-arch` session. Check the prompt first.

## Prerequisites

- An Arch-based system with `pacman`, `systemd`, `acl` (`setfacl`), and kernel
  ≥ 5.13 (native rootless overlayfs; older kernels fall back to
  `fuse-overlayfs`).
- `sudo` access for the operator.
- This repository cloned somewhere the operator owns. It is private — clone it
  as the operator (a user with GitHub access). The `dos-arch` service user
  never needs GitHub credentials and never clones anything.

## Steps

### 1 — Host bootstrap (operator, sudo)

From the repo root:

```bash
sudo ./install/host-setup.sh
```

Creates the `dos-arch` user, ensures subuid/subgid ranges, installs
`docker docker-buildx slirp4netns fuse-overlayfs`, leaves the rootful
`docker.service` disabled, enables linger, and stages `install/` + `docker/`
into `/home/dos-arch/setup/`.

### 2 — Rootless Docker (as dos-arch)

Enter a real `dos-arch` session. Use `machinectl`, **not** `sudo -iu` —
rootless Docker's `systemctl --user` needs a user systemd manager and
`XDG_RUNTIME_DIR`, which only a login session provides:

```bash
sudo machinectl shell dos-arch@
cd ~/setup
./install/rootless-setup.sh
```

`rootless-setup.sh` detects the installed Docker version, fetches the
matching rootless-extras (the Arch `docker` package ships no rootless
wrapper scripts), runs the official setuptool, persists env, and verifies
with `docker run hello-world`.

It appends `PATH` + `DOCKER_HOST` to `~/.bashrc`. If you continue in the
**same** session for later steps, run `source ~/.bashrc` first (or open a
fresh `dos-arch` session) so those take effect.

### 3 — Create `.env` (operator)

The credential broker reads two secrets from a repo-root `.env`. It is not in
the repo — create it from the template **as the operator**, in your clone:

```bash
cd /path/to/dos-arch          # your clone
cp .env.example .env
```

Fill the two values in `.env`:

- **`ANTHROPIC_API_KEY`** — from the Anthropic Console.
- **`GITHUB_TOKEN`** — for git-over-HTTPS through the broker. Two ways:
  - *Recommended:* a **fine-grained PAT** scoped to just the repos shells
    need. The broker holds this token, so a narrow scope bounds the blast
    radius if it is ever compromised.
  - *Quick (dev/test):* if `gh` is authenticated on the host, `gh auth token`
    prints a usable token — but it is account-wide. Wire it in without
    retyping:
    `sed -i "s|^GITHUB_TOKEN=.*|GITHUB_TOKEN=$(gh auth token)|" .env`

`.env` is gitignored — confirm with `git check-ignore .env`.

Then grant the `dos-arch` user access to your clone. It must traverse your
home directory and **read *and write*** the whole clone — `make launch`,
`make bootstrap` and `make install` run *as* `dos-arch`, and they write
into the clone: `run.py` renders `shells/<name>/CLAUDE.md` and opens
session rows in `shell_db.db`; `make install`/`make bootstrap` write
`.venv/`, `node_modules/`, and the DB. All of that is gitignored, so it
never collides with the operator's `git pull`.

```bash
setfacl -m u:dos-arch:x /home/<operator>
setfacl -R    -m u:dos-arch:rwX /path/to/dos-arch   # existing files
setfacl -R -d -m u:dos-arch:rwX /path/to/dos-arch   # default ACL — inherited by files created later
```

Run the grants **after** creating `.env` so it is covered too. The default
ACL (`-d`) is load-bearing: `shell_db.db` and `node_modules/` do not exist
yet at this point, so without it the files `dos-arch` creates later would
not be covered. The operator still owns the clone and runs `git pull`;
`dos-arch` never needs GitHub credentials and never clones anything.

### 4 — Build images + start the broker (as dos-arch)

`build-image.sh` and `broker-up.sh` need the **full repo** — `build-image.sh`
builds the broker image from `shell_core/broker/`, and `broker-up.sh` reads
secrets from the repo-root `.env`. The Phase 0–1 `~/setup` staging (just
`install/` + `docker/`) is **not** enough: run from `~/setup` and the broker
build fails. Run these from the operator's clone:

```bash
sudo machinectl shell dos-arch@     # skip if already in a dos-arch session
source ~/.bashrc                    # ensure PATH + DOCKER_HOST are set
cd /path/to/dos-arch                # the operator's clone — NOT ~/setup
./install/build-image.sh            # dos-shell + dos-broker + dos-api; optional pinned Claude version
./install/broker-up.sh              # dos-net network + dos-broker container
```

`build-image.sh` builds all three images (`dos-shell`, `dos-broker`,
`dos-api`) and runs `claude --version` inside `dos-shell`. Pin the Claude
Code version for a reproducible shell image:
`./install/build-image.sh 2.1.133`. `broker-up.sh` creates `dos-net`,
(re)starts the `dos-broker` container with `--env-file .env`, and health-
checks it. If `dos-arch` cannot read `.env`, re-run the step 3 `setfacl`
grants.

The `dos-api` image is built here, but its container is started later — by
`./install/api-up.sh`, after `make bootstrap` has created the substrate DB
(`api-up.sh` bind-mounts and requires `shell_core/shell_db.db`). See
**Cold bootstrap** in the main [README](../README.md#cold-bootstrap).

### 5 — Verify any time (as dos-arch)

```bash
docker run --rm hello-world
docker run --rm dos-shell:latest claude --version
docker run --rm --network dos-net --entrypoint python dos-broker:latest \
  -c "import urllib.request as u; print(u.urlopen('http://dos-broker:8788/health').read().decode())"
```

## Scripts

| Script | Runs as | Runs from | Does |
|---|---|---|---|
| `host-setup.sh`     | operator (sudo) | repo clone | service user, packages, linger, staging |
| `rootless-setup.sh` | `dos-arch`  | `~/setup` or clone | rootless Docker install + start + verify |
| `build-image.sh`    | `dos-arch`  | repo clone | build + verify `dos-shell` + `dos-broker` + `dos-api` |
| `broker-up.sh`      | `dos-arch`  | repo clone | `dos-net` network + `dos-broker` container |
| `api-up.sh`         | `dos-arch`  | repo clone | `dos-net` network + `dos-api` container (run after `make bootstrap`) |
| `teardown.sh`       | `dos-arch`  | `~/setup` or clone | remove containers/images + rootless Docker |

All idempotent — safe to re-run.

## Teardown — rebuild or complete removal

`teardown.sh` is the inverse of the install. It runs in three phases.

**Phase 1 — `dos-arch`-side.** As `dos-arch`, `teardown.sh` prunes all
containers / images / networks / volumes and uninstalls rootless Docker,
then prints the Phase-2 sudo block:

```bash
sudo machinectl shell dos-arch@
~/setup/install/teardown.sh        # or ./install/teardown.sh from the clone
exit
```

**Phase 2 — host-level (sudo).** As the operator, remove the `dos-arch`
service user and its host footprint:

```bash
sudo loginctl disable-linger dos-arch
sudo loginctl terminate-user dos-arch          # stop its running user manager
sudo userdel -r dos-arch                       # removes /home/dos-arch wholesale
sudo sed -i '/^dos-arch:/d' /etc/subuid /etc/subgid
```

Optional — package removal. `pacman` refuses if a package still has
dependents (on CachyOS, `fuse-overlayfs` is commonly required by
`profile-sync-daemon`) — drop any such package from the list, or skip this
step entirely: the packages are inert once the `dos-arch` user is gone.

```bash
sudo pacman -Rns docker docker-buildx slirp4netns fuse-overlayfs
```

**To rebuild:** stop here — the host is clean — and start again at step 1.

**Phase 3 — complete removal (operator-side).** Phases 1-2 leave the
operator's clone and shell config untouched. For a *complete* rip-out,
also remove these — as the operator:

```bash
setfacl -b ~                                   # drop the dos-arch traverse ACL on your home
rm -rf /path/to/dos-arch                       # the clone — INCLUDING .env (real secrets)
sudo rm -f /etc/sudoers.d/launch-dos-arch      # the NOPASSWD drop-in, if you added one
rm -rf ~/db_backups/dos-arch                   # boot DB snapshots, if any
```

Remove the `launch-dos-arch` shortcut from your shell:

- **fish:** `functions --erase launch-dos-arch; rm -f ~/.config/fish/functions/launch-dos-arch.fish`
- **bash:** delete the `launch-dos-arch` line from `~/.bashrc`

`.env` carried real credentials (`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`). If the
host is shared or untrusted, rotate those keys after removal — deletion
clears them from disk, not from anywhere they were already used.

## Notes / troubleshooting

- **Why a separate `dos-arch` user.** Rootless Docker under a dedicated
  unprivileged service user is the OS-level sandbox boundary. sudo is used
  only by `host-setup.sh`; the daily launch path never escalates.
- **`sudo` prompts for a `dos-arch` password.** You are running `sudo` inside
  a `dos-arch` session — `dos-arch` is passwordless and not a sudoer. Ctrl-C,
  check the shell prompt, and re-read *The two users* above. Commands queued
  after the failed `sudo` line may still run; verify what actually executed.
- **The `docker` package has no rootless scripts.** Arch/CachyOS package
  `dockerd`/`containerd` but not `dockerd-rootless*.sh`. We fetch the
  version-matched scripts + `rootlesskit` from `download.docker.com`;
  `dockerd`/`containerd` stay pacman-managed and auto-update via `pacman -Syu`.
- **cgroup v2 delegation.** Modern systemd delegates cpu/cpuset/io/memory/pids
  to user sessions by default. If the setuptool warns about delegation, create
  `/etc/systemd/system/user@.service.d/delegate.conf`:

  ```ini
  [Service]
  Delegate=cpu cpuset io memory pids
  ```

  then `sudo systemctl daemon-reload` and re-run `rootless-setup.sh`.
- **Unprivileged user namespaces.** If the setuptool reports user namespaces
  are disabled: `sudo sysctl -w kernel.unprivileged_userns_clone=1` (persist
  in `/etc/sysctl.d/`). Arch defaults to enabled.
