#!/usr/bin/env bash
# broker-up.sh — bring up the credential broker container.
#
# Run as the operator, after build-image.sh.
#
#   ./install/broker-up.sh
#
# Creates the shared `dos-net` network (idempotent) and (re)starts the
# `dos-broker` container on it. Shell containers join dos-net and reach the
# broker by Docker DNS name (http://dos-broker:8788).
#
# As of Phase 1 the broker no longer reads provider keys from the environment.
# Secrets live in an envelope-encrypted store the broker owns, on a docker
# NAMED VOLUME (`${SECRETS_VOL}` -> /secrets: secrets.db + the KEK master.key).
# A named volume (not a host bind mount) so the non-root broker can write it
# under rootless docker — see the Dockerfile note. The only thing passed from
# the environment is BROKER_ADMIN_TOKEN, which gates the secret-management
# admin API — NOT a provider credential.
#
# PREREQUISITE: the store must be seeded before egress works — run
# ./install/secrets-init.sh first (generates the KEK + imports .env keys). An
# empty store => egress returns 502 until a secret is set there or via the Keys UI.
#
# Idempotent: safe to re-run.
set -euo pipefail

ENV_FILE="${HOME}/.config/dos-arch/.env"
SECRETS_VOL="dos-broker-secrets"   # docker named volume: secrets.db + master.key
NET="dos-net"
NAME="dos-broker"
IMAGE="dos-broker:latest"

command -v docker >/dev/null || {
  echo "ERROR: docker not on PATH — run ./install/rootless-setup.sh first." >&2
  exit 1
}
docker image inspect "${IMAGE}" >/dev/null 2>&1 || {
  echo "ERROR: ${IMAGE} not built — run ./install/build-image.sh first." >&2
  exit 1
}

# Admin token gates the secret-management API. Extract it from the env file if
# present; pass ONLY this one value into the container (never the whole .env, so
# provider keys never enter the broker's environment). The token value is never
# echoed.
ADMIN_ARGS=()
if [[ -r "${ENV_FILE}" ]] && grep -q '^BROKER_ADMIN_TOKEN=' "${ENV_FILE}"; then
  TOKEN="$(grep -E '^BROKER_ADMIN_TOKEN=' "${ENV_FILE}" | head -1 | cut -d= -f2- | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//')"
  ADMIN_ARGS=(-e "BROKER_ADMIN_TOKEN=${TOKEN}")
  echo "    admin token: wired (admin API enabled)"
else
  echo "    admin token: BROKER_ADMIN_TOKEN not in ${ENV_FILE} — admin API will be DISABLED" >&2
fi

echo "==> [1/3] network ${NET}"
docker network inspect "${NET}" >/dev/null 2>&1 \
  || docker network create "${NET}" >/dev/null
echo "    ${NET} ready"

echo "==> [2/3] (re)start ${NAME}"
docker rm -f "${NAME}" >/dev/null 2>&1 || true
# Published to 127.0.0.1:8788 so the HOST dispatcher (pm2, not on dos-net) can
# route provider calls through the broker too (Phase 1, I5) — it stays
# dos-net-internal for shell containers and bound to localhost for the host,
# never the public interface. (Per-client auth on the broker is Phase 2.)
docker run -d --name "${NAME}" --network "${NET}" \
  -p 127.0.0.1:8788:8788 \
  -v "${SECRETS_VOL}:/secrets" \
  -e "BROKER_SECRETS_DB=/secrets/secrets.db" \
  -e "BROKER_KEK_PATH=/secrets/master.key" \
  "${ADMIN_ARGS[@]}" \
  --restart unless-stopped "${IMAGE}" >/dev/null
echo "    ${NAME} running on ${NET} + 127.0.0.1:8788 (secrets on volume ${SECRETS_VOL})"

echo "==> [3/3] health check (from a throwaway container on ${NET})"
sleep 1
docker run --rm --network "${NET}" --entrypoint python "${IMAGE}" -c \
  "import urllib.request as u; print(u.urlopen('http://${NAME}:8788/health').read().decode())"
echo "    broker reachable as http://${NAME}:8788 on ${NET}"
