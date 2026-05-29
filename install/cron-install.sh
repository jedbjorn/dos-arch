#!/usr/bin/env bash
# cron-install.sh — install dos-arch's daily host-side cron jobs.
#
# Run as the operator, once, after the substrate is bootstrapped.
#
#   ./install/cron-install.sh
#
# Installs three entries, each independently idempotent (own MARKER tag):
#
#   1. dr_* catalogue sync — 04:00 daily, `make db-sync`. The in-container
#      FastAPI-startup sync can't reach `git` or `ecosystem.config.cjs` and
#      only fires on container restart; this host-side cron is the only
#      *automatic* full (9/9 surface) sync. Runs land in dr_sync_runs with
#      trigger_kind='cron' (DR_SYNC_TRIGGER=cron) — a stale newest run_at
#      means the cron stopped firing.
#
#   2. Ollama Cloud model catalog sync — 04:15 daily, `make sync-cloud-models`.
#      Refreshes the `models` rows for provider='ollama_cloud' from Ollama
#      Cloud's anonymous /api/tags. Liveness check: SELECT MAX(last_verified)
#      FROM models WHERE provider='ollama_cloud' — stale means the cron died.
#      API startup also runs this sync, so a freshly-booted substrate doesn't
#      wait until 04:15 for a refresh.
#
#   3. Anthropic + OpenAI catalog sync — 04:30 daily, `make sync-remote-models`.
#      Refreshes the `models` rows for the first-party SDK providers from each
#      provider's /v1/models. Unlike the cloud sync this read needs the
#      provider API keys; the script loads them from ~/.config/dos-arch/.env.
#      Liveness check: SELECT MAX(last_verified) FROM models WHERE provider IN
#      ('anthropic','openai'). API startup also runs this sync.
#
# Re-running this script replaces all entries in place, never duplicates.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"
LOG_DIR="${HOME}/db_backups/dos-arch"

DR_MARKER="# dos-arch:dr-sync-cron"
DR_LOG="${LOG_DIR}/dr_sync_cron.log"
DR_CMD="cd ${REPO} && DR_SYNC_TRIGGER=cron make db-sync >> ${DR_LOG} 2>&1"
DR_LINE="0 4 * * * ${DR_CMD}  ${DR_MARKER}"

CLOUD_MARKER="# dos-arch:cloud-model-sync-cron"
CLOUD_LOG="${LOG_DIR}/cloud_model_sync_cron.log"
CLOUD_CMD="cd ${REPO} && make sync-cloud-models >> ${CLOUD_LOG} 2>&1"
CLOUD_LINE="15 4 * * * ${CLOUD_CMD}  ${CLOUD_MARKER}"

REMOTE_MARKER="# dos-arch:remote-model-sync-cron"
REMOTE_LOG="${LOG_DIR}/remote_model_sync_cron.log"
REMOTE_CMD="cd ${REPO} && make sync-remote-models >> ${REMOTE_LOG} 2>&1"
REMOTE_LINE="30 4 * * * ${REMOTE_CMD}  ${REMOTE_MARKER}"

command -v crontab >/dev/null || {
  echo "ERROR: crontab not found — install cron (e.g. 'apt install cron') and retry." >&2
  exit 1
}

mkdir -p "${LOG_DIR}"

# Rebuild the crontab: drop any prior entries we own (by MARKER), append the
# fresh ones. `crontab -l` exits non-zero when no crontab exists yet — tolerate.
current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "${current}" | grep -vF "${DR_MARKER}" | grep -vF "${CLOUD_MARKER}" | grep -vF "${REMOTE_MARKER}" || true)"
{
  [ -n "${filtered}" ] && printf '%s\n' "${filtered}"
  printf '%s\n' "${DR_LINE}"
  printf '%s\n' "${CLOUD_LINE}"
  printf '%s\n' "${REMOTE_LINE}"
} | crontab -

echo "==> dos-arch cron jobs installed"
echo
echo "    [1] dr_* catalogue sync"
echo "        schedule : 04:00 daily"
echo "        command  : ${DR_CMD}"
echo "        verify   : crontab -l | grep dr-sync-cron"
echo "        runs log : SELECT run_at, trigger_kind, had_error FROM dr_sync_runs ORDER BY run_id DESC;"
echo
echo "    [2] Ollama Cloud model catalog sync"
echo "        schedule : 04:15 daily"
echo "        command  : ${CLOUD_CMD}"
echo "        verify   : crontab -l | grep cloud-model-sync-cron"
echo "        liveness : SELECT MAX(last_verified) FROM models WHERE provider='ollama_cloud';"
echo
echo "    [3] Anthropic + OpenAI catalog sync"
echo "        schedule : 04:30 daily"
echo "        command  : ${REMOTE_CMD}"
echo "        verify   : crontab -l | grep remote-model-sync-cron"
echo "        liveness : SELECT MAX(last_verified) FROM models WHERE provider IN ('anthropic','openai');"
