#!/usr/bin/env bash
# setup.sh — one-command install for the dos-arch substrate.
#
# Run AS THE OPERATOR (your normal login), from anywhere in the repo:
#
#   ./install/setup.sh
#
# dos-arch is an API system: the API, UI, browser-chat dispatcher and
# model-sync all run as host pm2 processes; the credential broker is the only
# container (it holds secrets). There are no terminal shells and no per-shell
# containers — shells are created and operated through the API + dispatcher.
#
# Single-user model: rootless Docker, the substrate, and the broker container
# all run as the operator. There is no service user, no machinectl, no ACLs.
# The only step that needs root is host-setup.sh; setup.sh sudo's it
# internally — sudo prompts for YOUR password.
#
# Two interactive moments, both up front: the sudo password (step 1) and the
# first-admin username/password (step 2, `make bootstrap`). Everything after
# runs unattended.
#
# Precondition — the secrets file must exist (a script cannot author it):
#   mkdir -p ~/.config/dos-arch
#   cp .env.example ~/.config/dos-arch/.env   # then fill in the keys
#
# Idempotent — safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${HOME}/.config/dos-arch/.env"
DB="${REPO_ROOT}/shell_core/shell_db.db"

# ── preconditions ─────────────────────────────────────────────────────────────
if [[ ${EUID} -eq 0 ]]; then
  echo "ERROR: run as the operator (your normal login), not root — no leading sudo." >&2
  echo "       setup.sh escalates internally only where it must." >&2
  exit 1
fi
command -v sudo >/dev/null || { echo "ERROR: 'sudo' not found on PATH." >&2; exit 1; }
if [[ ! -r "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} is missing — it carries secrets a script cannot author." >&2
  echo "       mkdir -p ~/.config/dos-arch" >&2
  echo "       cp '${REPO_ROOT}/.env.example' '${ENV_FILE}'   # then fill it in" >&2
  echo "       Fill in ANTHROPIC_API_KEY + GITHUB_TOKEN — see install/README.md." >&2
  exit 1
fi

cd "${REPO_ROOT}"
echo "=== dos-arch substrate setup ==="
echo "    operator : $(id -un)"
echo "    repo     : ${REPO_ROOT}"
echo "    sudo will prompt for YOUR password (step 1 only)."

# ── [1/8] host bootstrap (root) ───────────────────────────────────────────────
echo
echo ">>> [1/8] host-setup.sh — system packages + rootless prerequisites"
sudo ./install/host-setup.sh

# ── [2/8] substrate DB + first admin user (interactive) ───────────────────────
echo
echo ">>> [2/8] make bootstrap — substrate DB + first admin user"
if [[ -f "${DB}" ]]; then
  echo "    ${DB} already exists — skipping bootstrap."
  echo "    (to recreate: 'make db-backup', remove the DB, re-run setup.sh)"
else
  make bootstrap
fi

# ── [3/8] Python venv + UI deps ───────────────────────────────────────────────
echo
echo ">>> [3/8] make install — Python venv + UI npm dependencies"
make install

# ── [4/8] rootless Docker ─────────────────────────────────────────────────────
echo
echo ">>> [4/8] rootless-setup.sh — install + start rootless Docker"
./install/rootless-setup.sh

# ── [5/8] build the broker image ──────────────────────────────────────────────
echo
echo ">>> [5/9] build-image.sh — dos-broker image (the only container)"
./install/build-image.sh

# ── [6/9] seed the encrypted secret store ─────────────────────────────────────
# The broker reads provider keys from an envelope-encrypted store, not the
# environment. Seed it (KEK + store + one-time .env key import) BEFORE broker-up,
# else the broker comes up empty and egress returns 502. Idempotent and
# non-clobbering — a re-run keeps existing secrets + BROKER_ADMIN_TOKEN.
echo
echo ">>> [6/9] secrets-init.sh — KEK + encrypted store + one-time .env key import"
./install/secrets-init.sh

# ── [7/9] credential broker ───────────────────────────────────────────────────
echo
echo ">>> [7/9] broker-up.sh — credential broker container"
./install/broker-up.sh

# ── [8/9] host services (pm2) ─────────────────────────────────────────────────
# make up brings up all four host apps: API (uvicorn on 127.0.0.1:8001), UI,
# browser-chat dispatcher, and model-sync. migrate runs first so the live
# schema is current before the API + dispatcher open the DB.
echo
echo ">>> [8/9] make migrate + make up — apply migrations, pm2 starts API/UI/dispatcher/model-sync"
make migrate
make up

# ── [9/9] post-install — catalogue cron + hardware/model capture ──────────────
# Both are cheap and deterministic, so they belong in the install. sync-models
# probes the host into user_hardware (always works) and reads Ollama's installed
# set into the models registry (needs Ollama running) — if Ollama is absent the
# hardware probe still lands and the model read is skipped, never fatal.
echo
echo ">>> [9/9] post-install — catalogue cron + hardware/model capture"
./install/cron-install.sh \
  || echo "    WARNING: cron install failed — run ./install/cron-install.sh by hand"
make sync-models \
  || echo "    NOTE: Ollama not reachable — hardware captured, model sync skipped; run 'make sync-models' once Ollama is up"

cat <<EOF

=== dos-arch substrate ready ===
  rootless Docker · dos-broker image · dos-broker container on dos-net ·
  API + UI + dispatcher + model-sync under pm2 · nightly catalogue cron.

  make health     GET /health
  make status     pm2 process list
  make logs       pm2 logs

Shells are created and operated through the API + browser-chat UI
(http://127.0.0.1:5174), not a terminal. Local models are optional — install
Ollama, pull a model, then re-run 'make sync-models'. See the README for
daily commands.
EOF
