#!/usr/bin/env bash
# api-up.sh — bring up the substrate API container.
#
# Run AS the dos-arch user (rootless Docker), after build-image.sh.
#
#   ./install/api-up.sh
#
# Creates the shared `dos-net` network (idempotent) and (re)starts the
# `dos-api` container on it. Shell containers reach it by Docker DNS name
# (http://dos-api:8000); the host UI reaches it on 127.0.0.1:8000. The
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

command -v docker >/dev/null || {
  echo "ERROR: docker not on PATH — run rootless-setup.sh, then open a fresh shell." >&2
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

echo "==> [1/5] network ${NET}"
docker network inspect "${NET}" >/dev/null 2>&1 \
  || docker network create "${NET}" >/dev/null
echo "    ${NET} ready"

echo "==> [2/5] stop ${NAME} (migrations apply with no DB writer)"
docker rm -f "${NAME}" >/dev/null 2>&1 || true

# Apply pending DB migrations before the API serves. migrate.py exits
# non-zero on failure → set -e aborts here, leaving dos-api stopped: a
# half-migrated DB never goes live. Restore from the snapshot it prints.
echo "==> [3/5] pending DB migrations"
python3 "${CORE}/scripts/migrate.py"

echo "==> [4/5] start ${NAME}"
docker run -d --name "${NAME}" --network "${NET}" \
  -v "${CORE}:/substrate/shell_core" \
  -p 127.0.0.1:8000:8000 \
  --restart unless-stopped "${IMAGE}" >/dev/null
echo "    ${NAME} running on ${NET}, published to 127.0.0.1:8000"

echo "==> [5/5] health check"
sleep 2
docker run --rm --network "${NET}" --entrypoint python "${IMAGE}" -c \
  "import urllib.request as u; print(u.urlopen('http://${NAME}:8000/health').read().decode())"
echo "    dos-api reachable as http://${NAME}:8000 on ${NET}"
