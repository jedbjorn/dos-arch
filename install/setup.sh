#!/usr/bin/env bash
# setup.sh — one-command install for the dos-arch substrate.
#
# Run AS THE OPERATOR (your normal login), from anywhere in the repo:
#
#   ./install/setup.sh [CLAUDE_VERSION]
#
# Single-user model: rootless Docker, the substrate, and every container run
# as the operator. There is no service user, no machinectl, no ACLs. The only
# step that needs root is host-setup.sh; setup.sh sudo's it internally — sudo
# prompts for YOUR password.
#
# Two interactive moments, both up front: the sudo password (step 1) and the
# first-admin username/password (step 2, `make bootstrap`). Everything after
# runs unattended.
#
# Precondition — the secrets file must exist (a script cannot author it):
#   mkdir -p ~/.config/dos-arch
#   cp .env.example ~/.config/dos-arch/.env   # then fill in the two keys
#
# Idempotent — safe to re-run.
set -euo pipefail

CLAUDE_VERSION="${1:-stable}"
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

# ── [1/9] host bootstrap (root) ───────────────────────────────────────────────
echo
echo ">>> [1/9] host-setup.sh — system packages + rootless prerequisites"
sudo ./install/host-setup.sh

# ── [2/9] substrate DB + first admin user (interactive) ───────────────────────
echo
echo ">>> [2/9] make bootstrap — substrate DB + first admin user"
if [[ -f "${DB}" ]]; then
  echo "    ${DB} already exists — skipping bootstrap."
  echo "    (to recreate: 'make db-backup', remove the DB, re-run setup.sh)"
else
  make bootstrap
fi

# ── [3/9] Python venv + UI deps ───────────────────────────────────────────────
echo
echo ">>> [3/9] make install — Python venv + UI npm dependencies"
make install

# ── [4/9] rootless Docker ─────────────────────────────────────────────────────
echo
echo ">>> [4/9] rootless-setup.sh — install + start rootless Docker"
./install/rootless-setup.sh

# ── [5/9] build images ────────────────────────────────────────────────────────
echo
echo ">>> [5/9] build-image.sh — dos-shell / dos-broker / dos-api images"
./install/build-image.sh "${CLAUDE_VERSION}"

# ── [6/9] credential broker ───────────────────────────────────────────────────
echo
echo ">>> [6/9] broker-up.sh — credential broker container"
./install/broker-up.sh

# ── [7/9] substrate API ───────────────────────────────────────────────────────
echo
echo ">>> [7/9] api-up.sh — substrate API container"
./install/api-up.sh

# ── [8/9] host services ───────────────────────────────────────────────────────
echo
echo ">>> [8/9] make up — pm2 starts the UI + browser-chat dispatcher"
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
  rootless Docker · dos-shell/dos-broker/dos-api images · dos-broker + dos-api
  containers on dos-net · UI + dispatcher under pm2 · nightly catalogue cron.

  make launch     auth, pick a shell, boot it into its container
  make health     GET /health
  make status     pm2 process list

Local models are optional — install Ollama, pull a model, then re-run
'make sync-models'. See the README for daily commands.
EOF
