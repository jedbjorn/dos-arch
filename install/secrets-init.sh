#!/usr/bin/env bash
# secrets-init.sh — initialize the broker's encrypted secret store (Phase 1).
#
# Run as the operator, once, after build-image.sh and before broker-up.sh on a
# fresh install (and re-runnable any time — every step is idempotent).
#
#   ./install/secrets-init.sh
#
# What it does:
#   1. Generates BROKER_ADMIN_TOKEN into ~/.config/dos-arch/.env if absent. This
#      token gates the broker's secret-management admin API (and is handed to
#      the substrate API so the Keys UI can call it). Never a provider key.
#   2. Creates the secrets volume + the KEK (master.key) + the store (secrets.db)
#      by running `secrets_store init` INSIDE the broker image — that is where
#      `cryptography` lives; nothing crypto runs on the host.
#   3. Imports existing provider keys from .env into the encrypted store
#      (one-time migration). The import is a throwaway container with --env-file
#      so it can read the plaintext keys ONCE; the long-running broker
#      (broker-up.sh) never gets --env-file, so it holds no provider keys.
#
# After this: `./install/broker-up.sh` starts the broker reading from the store.
# Rotate keys later via the Keys UI (no restart) — this script is only the seed.
set -euo pipefail

ENV_FILE="${HOME}/.config/dos-arch/.env"
SECRETS_DIR="${HOME}/.config/dos-arch/broker"
IMAGE="dos-broker:latest"
# Provider secrets to migrate from .env on first run. Add names here as new
# providers are wired; import is non-clobbering so re-runs are safe.
IMPORT_NAMES=(ANTHROPIC_API_KEY OPENAI_API_KEY GITHUB_TOKEN)

command -v docker >/dev/null || { echo "ERROR: docker not on PATH." >&2; exit 1; }
docker image inspect "${IMAGE}" >/dev/null 2>&1 || {
  echo "ERROR: ${IMAGE} not built — run ./install/build-image.sh first." >&2
  exit 1
}
mkdir -p "$(dirname "${ENV_FILE}")" "${SECRETS_DIR}"
chmod 700 "${SECRETS_DIR}"
touch "${ENV_FILE}"; chmod 600 "${ENV_FILE}"

echo "==> [1/3] admin token"
if grep -q '^BROKER_ADMIN_TOKEN=' "${ENV_FILE}"; then
  echo "    BROKER_ADMIN_TOKEN already set — leaving it"
else
  # 32 random bytes hex. openssl is ubiquitous; the value is never echoed.
  printf 'BROKER_ADMIN_TOKEN=%s\n' "$(openssl rand -hex 32)" >> "${ENV_FILE}"
  echo "    BROKER_ADMIN_TOKEN generated -> ${ENV_FILE}"
fi

echo "==> [2/3] KEK + store (inside ${IMAGE})"
# init: generates /secrets/master.key (0600) + secrets.db if absent. Idempotent.
docker run --rm -v "${SECRETS_DIR}:/secrets" \
  -e BROKER_SECRETS_DB=/secrets/secrets.db -e BROKER_KEK_PATH=/secrets/master.key \
  -w /app \
  --entrypoint python "${IMAGE}" -m secrets_store init

echo "==> [3/3] import provider keys from .env (one-time, non-clobbering)"
# --env-file gives THIS throwaway container the plaintext keys just long enough
# to encrypt them into the store. import-env skips names already stored and
# names absent from the env, so re-runs never clobber a rotated value.
docker run --rm -v "${SECRETS_DIR}:/secrets" \
  --env-file "${ENV_FILE}" \
  -e BROKER_SECRETS_DB=/secrets/secrets.db -e BROKER_KEK_PATH=/secrets/master.key \
  -w /app \
  --entrypoint python "${IMAGE}" -m secrets_store import-env "${IMPORT_NAMES[@]}"

echo
echo "==> secret store ready at ${SECRETS_DIR}"
echo "    next: ./install/broker-up.sh   (starts the broker reading from the store)"
echo "    verify (no plaintext): docker run --rm -v ${SECRETS_DIR}:/secrets \\"
echo "      -e BROKER_SECRETS_DB=/secrets/secrets.db -w /app --entrypoint python ${IMAGE} \\"
echo "      -m secrets_store list"
