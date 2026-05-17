#!/usr/bin/env bash
# broker-up.sh — bring up the credential broker container.
#
# Run AS the dos-arch user (rootless Docker), after build-image.sh.
#
#   ./install/broker-up.sh
#
# Creates the shared `dos-net` network (idempotent) and (re)starts the
# `dos-broker` container on it. Shell containers join dos-net and reach the
# broker by Docker DNS name (http://dos-broker:8788). Secrets are read from
# the repo-root `.env` at run time via --env-file — never baked into the
# image. Idempotent: safe to re-run (e.g. after editing `.env`).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"
ENV_FILE="${REPO}/.env"
NET="dos-net"
NAME="dos-broker"
IMAGE="dos-broker:latest"

command -v docker >/dev/null || {
  echo "ERROR: docker not on PATH — run rootless-setup.sh, then open a fresh shell." >&2
  exit 1
}
docker image inspect "${IMAGE}" >/dev/null 2>&1 || {
  echo "ERROR: ${IMAGE} not built — run ./install/build-image.sh first." >&2
  exit 1
}
[[ -r "${ENV_FILE}" ]] || {
  echo "ERROR: cannot read ${ENV_FILE}" >&2
  echo "       The broker loads ANTHROPIC_API_KEY + GITHUB_TOKEN from it." >&2
  echo "       If the repo is in another user's home, grant read access:" >&2
  echo "         setfacl -m u:\$(id -un):r ${ENV_FILE}" >&2
  exit 1
}

echo "==> [1/3] network ${NET}"
docker network inspect "${NET}" >/dev/null 2>&1 \
  || docker network create "${NET}" >/dev/null
echo "    ${NET} ready"

echo "==> [2/3] (re)start ${NAME}"
docker rm -f "${NAME}" >/dev/null 2>&1 || true
docker run -d --name "${NAME}" --network "${NET}" \
  --env-file "${ENV_FILE}" --restart unless-stopped "${IMAGE}" >/dev/null
echo "    ${NAME} running on ${NET}"

echo "==> [3/3] health check (from a throwaway container on ${NET})"
sleep 1
docker run --rm --network "${NET}" --entrypoint python "${IMAGE}" -c \
  "import urllib.request as u; print(u.urlopen('http://${NAME}:8788/health').read().decode())"
echo "    broker reachable as http://${NAME}:8788 on ${NET}"
