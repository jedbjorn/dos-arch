#!/usr/bin/env bash
# build-image.sh — build the dos-arch substrate images.
#
# Run AS the dos-arch user (rootless Docker), after rootless-setup.sh.
#
#   ./install/build-image.sh [CLAUDE_VERSION]
#
# Builds three images:
#   dos-shell  — the shell-instance image (credential-free; one per shell).
#   dos-broker — the credential broker (the trusted, secret-holding image).
#   dos-api    — the substrate API (memory) — a trusted service on dos-net.
#
# CLAUDE_VERSION defaults to "stable"; pass a pinned version (e.g. 2.1.133)
# for a fully reproducible shell image.
#
# Rolling history — no manual pruning. Before each rebuild the current
# :latest is rotated to :history-1, the old :history-1 to :history-2, and so
# on; anything past :history-<HISTORY_DEPTH> is dropped. Each image therefore
# keeps :latest plus the last HISTORY_DEPTH builds. Roll back with e.g.
#   docker tag dos-shell:history-1 dos-shell:latest
# Dangling layers from the rebuilds are pruned at the end automatically.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"
CLAUDE_VERSION="${1:-stable}"

HISTORY_DEPTH=3        # previous builds kept per image (tagged history-1..N)

command -v docker >/dev/null || {
  echo "ERROR: docker not on PATH — run rootless-setup.sh, then open a fresh shell." >&2
  exit 1
}

# rotate_history <image> — shift :latest -> :history-1 -> :history-2 -> …,
# dropping whatever falls past :history-<HISTORY_DEPTH>. Call BEFORE building
# a new :latest. No-op on the first build (there is no :latest yet).
rotate_history() {
  local img="$1" i
  docker image inspect "${img}:latest" >/dev/null 2>&1 || return 0
  docker rmi "${img}:history-${HISTORY_DEPTH}" >/dev/null 2>&1 || true
  for (( i = HISTORY_DEPTH - 1; i >= 1; i-- )); do
    docker tag "${img}:history-${i}" "${img}:history-$(( i + 1 ))" >/dev/null 2>&1 || true
  done
  docker tag "${img}:latest" "${img}:history-1" >/dev/null 2>&1 || true
}

echo "==> building dos-shell:latest (CLAUDE_VERSION=${CLAUDE_VERSION})"
rotate_history dos-shell
docker build --build-arg "CLAUDE_VERSION=${CLAUDE_VERSION}" \
  -t dos-shell:latest "${REPO}/docker/shell"
echo "==> verify dos-shell"
docker run --rm dos-shell:latest claude --version

# Broker build context is shell_core/broker/ (broker.py + requirements.txt);
# the Dockerfile lives under docker/broker/ and is pointed at with -f.
echo "==> building dos-broker:latest"
rotate_history dos-broker
docker build -f "${REPO}/docker/broker/Dockerfile" \
  -t dos-broker:latest "${REPO}/shell_core/broker"

# dos-api carries deps only — substrate code + DB are bind-mounted at run
# time — so the build context is just docker/api/ (the Dockerfile COPYs
# nothing).
echo "==> building dos-api:latest"
rotate_history dos-api
docker build -f "${REPO}/docker/api/Dockerfile" \
  -t dos-api:latest "${REPO}/docker/api"

# Drop dangling (untagged) layers left behind by the rebuilds. `prune` with
# no -a removes ONLY dangling images, so :latest and every :history-* tag is
# kept. Safe to run unconditionally: this is the dedicated rootless dos-arch
# Docker, so nothing outside the substrate is ever touched.
echo "==> pruning dangling images"
docker image prune -f >/dev/null

echo "    images built OK — dos-shell:latest, dos-broker:latest, dos-api:latest"
echo "    rolling history kept per image: history-1..${HISTORY_DEPTH} (older builds auto-dropped)"
echo "    next: ./install/broker-up.sh && ./install/api-up.sh"
