#!/usr/bin/env bash
# cron-install.sh — install the daily dr_* catalogue sync cron.
#
# Run as the operator, once, after the substrate is bootstrapped.
#
#   ./install/cron-install.sh
#
# Why this exists: the in-container FastAPI-startup sync can't reach `git` or
# `ecosystem.config.cjs`, so it silently no-ops dr_repo + dr_services — and it
# only fires on a container restart anyway. Nothing refreshes the catalogue
# while the container simply stays up. This cron is the only *automatic* full
# (9/9 surface) sync: host-side, daily, with git + node + the whole repo.
#
# It runs `make db-sync` with DR_SYNC_TRIGGER=cron so each run lands a row in
# dr_sync_runs (trigger_kind='cron') — query that table to confirm the cron is
# alive; a stale newest run_at means it stopped firing.
#
# Idempotent: re-running replaces the existing entry, never duplicates it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"
MARKER="# dos-arch:dr-sync-cron"          # idempotency tag — one line per host
LOG_DIR="${HOME}/db_backups/dos-arch"
LOG="${LOG_DIR}/dr_sync_cron.log"

command -v crontab >/dev/null || {
  echo "ERROR: crontab not found — install cron (e.g. 'apt install cron') and retry." >&2
  exit 1
}

mkdir -p "${LOG_DIR}"

# 04:00 daily. cd into the repo first so `make` finds the Makefile and the
# db-sync recipe's relative ./.venv path resolves. stdout/stderr append to the
# logfile — a belt-and-suspenders signal for the case dr_sync_runs can't catch
# (process died before its DB write, or cron never fired at all).
CRON_CMD="cd ${REPO} && DR_SYNC_TRIGGER=cron make db-sync >> ${LOG} 2>&1"
CRON_LINE="0 4 * * * ${CRON_CMD}  ${MARKER}"

# Rebuild the crontab: keep every line except a prior entry of ours, append the
# fresh one. `crontab -l` exits non-zero when no crontab exists yet — tolerate.
current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "${current}" | grep -vF "${MARKER}" || true)"
{
  [ -n "${filtered}" ] && printf '%s\n' "${filtered}"
  printf '%s\n' "${CRON_LINE}"
} | crontab -

echo "==> dr_* catalogue sync cron installed (dos-arch crontab)"
echo "    schedule : 04:00 daily"
echo "    command  : ${CRON_CMD}"
echo "    verify   : crontab -l | grep dr-sync-cron"
echo "    runs log : SELECT run_at, trigger_kind, had_error FROM dr_sync_runs ORDER BY run_id DESC;"
