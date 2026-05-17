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
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"
CLAUDE_VERSION="${1:-stable}"

command -v docker >/dev/null || {
  echo "ERROR: docker not on PATH — run rootless-setup.sh, then open a fresh shell." >&2
  exit 1
}

echo "==> building dos-shell:latest (CLAUDE_VERSION=${CLAUDE_VERSION})"
docker build --build-arg "CLAUDE_VERSION=${CLAUDE_VERSION}" \
  -t dos-shell:latest "${REPO}/docker/shell"
echo "==> verify dos-shell"
docker run --rm dos-shell:latest claude --version

# Broker build context is shell_core/broker/ (broker.py + requirements.txt);
# the Dockerfile lives under docker/broker/ and is pointed at with -f.
echo "==> building dos-broker:latest"
docker build -f "${REPO}/docker/broker/Dockerfile" \
  -t dos-broker:latest "${REPO}/shell_core/broker"

# dos-api carries deps only — substrate code + DB are bind-mounted at run
# time — so the build context is just docker/api/ (the Dockerfile COPYs
# nothing).
echo "==> building dos-api:latest"
docker build -f "${REPO}/docker/api/Dockerfile" \
  -t dos-api:latest "${REPO}/docker/api"

echo "    images built OK — dos-shell:latest, dos-broker:latest, dos-api:latest"
echo "    next: ./install/broker-up.sh && ./install/api-up.sh"
