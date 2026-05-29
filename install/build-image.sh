#!/usr/bin/env bash
# build-image.sh — build the dos-arch container image.
#
# Run as the operator, after rootless-setup.sh.
#
#   ./install/build-image.sh
#
# dos-arch is an API system: the API, UI, dispatcher and model-sync all run as
# host pm2 processes (see ecosystem.config.cjs). The credential broker is the
# ONE component that stays containerized — it holds secrets, so it gets a hard
# isolation boundary. There are no per-shell containers (no dos-shell) and the
# API is not a container (it was dos-api; moved host-side for WAL coherence,
# CC-095). So this builds a single image: dos-broker.
#
# Rolling history — no manual pruning. Before each rebuild the current
# :latest is rotated to :history-1, the old :history-1 to :history-2, and so
# on; anything past :history-<HISTORY_DEPTH> is dropped. Roll back with e.g.
#   docker tag dos-broker:history-1 dos-broker:latest
# Dangling layers from the rebuilds are pruned at the end automatically.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"

HISTORY_DEPTH=3        # previous builds kept per image (tagged history-1..N)

command -v docker >/dev/null || {
  echo "ERROR: docker not on PATH — run ./install/rootless-setup.sh first." >&2
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

# Broker build context is shell_core/broker/ (broker.py + requirements.txt);
# the Dockerfile lives under docker/broker/ and is pointed at with -f.
echo "==> building dos-broker:latest"
rotate_history dos-broker
docker build -f "${REPO}/docker/broker/Dockerfile" \
  -t dos-broker:latest "${REPO}/shell_core/broker"

# Drop dangling (untagged) layers left behind by the rebuilds. `prune` with
# no -a removes ONLY dangling images, so :latest and every :history-* tag is
# kept. Safe to run unconditionally: this is the dedicated rootless dos-arch
# Docker, so nothing outside the substrate is ever touched.
echo "==> pruning dangling images"
docker image prune -f >/dev/null

echo "    image built OK — dos-broker:latest"
echo "    rolling history kept: history-1..${HISTORY_DEPTH} (older builds auto-dropped)"
echo "    next: ./install/broker-up.sh, then 'make up' (API/UI/dispatcher/model-sync on pm2)"
