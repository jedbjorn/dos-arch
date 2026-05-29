#!/usr/bin/env bash
# api-up.sh — bring up the substrate API container.
#
# Run as the operator, after build-image.sh.
#
#   ./install/api-up.sh
#
# Creates the shared `dos-net` network (idempotent) and (re)starts the
# `dos-api` container on it. Shell containers reach it by Docker DNS name
# (http://dos-api:8000); the host UI reaches it on 127.0.0.1:8001. The
# substrate code + shell_db.db are bind-mounted from the repo at run time —
# never baked into the image, so `git pull` + a re-run updates the API.
# Idempotent: safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"
NET="dos-net"
NAME="dos-api"
IMAGE="dos-api:latest"
CORE="${REPO}/shell_core"
BROKER_BASE="http://dos-broker:8788"

command -v docker >/dev/null || {
  echo "ERROR: docker not on PATH — run ./install/rootless-setup.sh first." >&2
  exit 1
}
docker image inspect "${IMAGE}" >/dev/null 2>&1 || {
  echo "ERROR: ${IMAGE} not built — run ./install/build-image.sh first." >&2
  exit 1
}
[[ -f "${CORE}/shell_db.db" ]] || {
  echo "ERROR: ${CORE}/shell_db.db not found — run 'make bootstrap' first." >&2
  exit 1
}

echo "==> [1/6] network ${NET}"
docker network inspect "${NET}" >/dev/null 2>&1 \
  || docker network create "${NET}" >/dev/null
echo "    ${NET} ready"

echo "==> [2/6] stop ${NAME} (migrations apply with no DB writer)"
docker rm -f "${NAME}" >/dev/null 2>&1 || true

# Apply pending DB migrations before the API serves. migrate.py exits
# non-zero on failure → set -e aborts here, leaving dos-api stopped: a
# half-migrated DB never goes live. Restore from the snapshot it prints.
echo "==> [3/6] pending DB migrations"
python3 "${CORE}/scripts/migrate.py"

# Post-migration backfill: any shell row missing an api_key gets one. Pairs
# with migration 031 (adds the column) — pure SQL can't generate tokens.
# Idempotent — only fills NULLs.
python3 "${CORE}/scripts/backfill_shell_api_keys.py"

# Catalogue sync MUST run host-side: dr_repo needs `git` + the repo's .git,
# dr_services needs `node` + ecosystem.config.cjs — none of which exist in
# the dos-api image (python:3.12-slim, shell_core-only bind mount), so the
# API's in-container startup sync silently no-ops those two surfaces. This
# host-side run is the complete one. Prefer the venv python (has fastapi,
# so the apis/routers sync runs too); fall back to bare python3 — repos +
# services need only stdlib + subprocess. Non-fatal: best-effort refresh.
echo "==> [4/6] catalogue sync (host-side — git/node + full repo)"
DRSYNC_PY="${REPO}/.venv/bin/python3"
[[ -x "${DRSYNC_PY}" ]] || DRSYNC_PY="python3"
"${DRSYNC_PY}" "${CORE}/scripts/dr_sync.py" \
  || echo "    WARNING: catalogue sync reported errors (non-fatal)" >&2

# The remote model-catalog sync (Anthropic/OpenAI /v1/models) runs from the
# API — at startup and behind the /anthropicconfig + /openaiconfig "Refresh"
# button — and those reads need the provider API keys. The API stays
# CREDENTIAL-FREE for PROVIDER keys: it routes the reads through the broker
# (the one secret-holding component, already on dos-net), which injects the
# key on egress. We hand the API only the broker URL — not a provider secret.
#
# The API also backs the Keys UI (/keys), which manages secrets via the
# broker's admin API — so it needs the admin gate token (BROKER_ADMIN_TOKEN).
# That is the broker's own auth gate, NOT a provider credential; extracted from
# the env file, never echoed, and the only secret this container carries.
ENV_FILE="${HOME}/.config/dos-arch/.env"
ADMIN_ARGS=()
if [[ -r "${ENV_FILE}" ]] && grep -q '^BROKER_ADMIN_TOKEN=' "${ENV_FILE}"; then
  TOKEN="$(grep -E '^BROKER_ADMIN_TOKEN=' "${ENV_FILE}" | head -1 | cut -d= -f2- | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//')"
  ADMIN_ARGS=(-e "BROKER_ADMIN_TOKEN=${TOKEN}")
  echo "    admin token: wired (Keys UI enabled)"
else
  echo "    admin token: BROKER_ADMIN_TOKEN not in ${ENV_FILE} — Keys UI will be unavailable" >&2
fi

echo "==> [5/6] start ${NAME}"
docker run -d --name "${NAME}" --network "${NET}" \
  -v "${CORE}:/substrate/shell_core" \
  -p 127.0.0.1:8001:8000 \
  -e "BROKER_BASE=${BROKER_BASE}" \
  "${ADMIN_ARGS[@]}" \
  --restart unless-stopped "${IMAGE}" >/dev/null
echo "    ${NAME} running on ${NET}, published to 127.0.0.1:8001"

echo "==> [6/6] health check"
# Poll, don't single-shot: the FastAPI startup hooks (catalogue + cloud/remote
# model sync, the latter via the broker) delay uvicorn readiness past a fixed
# sleep, which would fail this check even though the container is fine.
ok=""
for _ in $(seq 1 20); do
  if docker run --rm --network "${NET}" --entrypoint python "${IMAGE}" -c \
      "import urllib.request as u; u.urlopen('http://${NAME}:8000/health', timeout=3)" \
      >/dev/null 2>&1; then
    ok=1; break
  fi
  sleep 1
done
if [[ -n "${ok}" ]]; then
  echo "    dos-api reachable as http://${NAME}:8000 on ${NET}"
else
  echo "    WARNING: ${NAME} did not pass health check within 20s — check 'docker logs ${NAME}'" >&2
fi
