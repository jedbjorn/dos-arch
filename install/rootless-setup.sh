#!/usr/bin/env bash
# rootless-setup.sh — install + start rootless Docker for the operator.
#
# Run AS THE OPERATOR, from your normal login shell — NO sudo. A desktop or
# SSH login already provides the user systemd manager and XDG_RUNTIME_DIR
# that rootless Docker needs: no service user, no machinectl hop.
#
#   ./install/rootless-setup.sh
#
# The Arch/CachyOS `docker` package ships dockerd/containerd but no rootless
# wrapper scripts, so this fetches docker-ce's version-matched rootless-extras
# (the wrapper scripts + rootlesskit) into ~/bin. dockerd/containerd stay
# pacman-managed and auto-update. Idempotent — safe to re-run.
set -euo pipefail

if [[ ${EUID} -eq 0 ]]; then
  echo "ERROR: run as the operator (your normal login) — not root, not sudo." >&2
  exit 1
fi
if [[ -z "${XDG_RUNTIME_DIR:-}" ]]; then
  echo "ERROR: no user session (XDG_RUNTIME_DIR unset)." >&2
  echo "       Run from a normal desktop or SSH login, not a detached shell." >&2
  exit 1
fi
command -v docker >/dev/null || {
  echo "ERROR: docker not installed — run 'sudo ./install/host-setup.sh' first." >&2
  exit 1
}

BIN="${HOME}/bin"
ARCH="$(uname -m)"

DOCKER_VERSION="$(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)"
[[ -n "${DOCKER_VERSION}" ]] || { echo "ERROR: cannot parse docker version." >&2; exit 1; }
echo "==> docker engine ${DOCKER_VERSION} (${ARCH})"

echo "==> [1/4] fetch rootless-extras into ${BIN}"
mkdir -p "${BIN}"
URL="https://download.docker.com/linux/static/stable/${ARCH}/docker-rootless-extras-${DOCKER_VERSION}.tgz"
curl -fsI "${URL}" >/dev/null || {
  echo "ERROR: no rootless-extras tarball for docker ${DOCKER_VERSION} (${ARCH})." >&2
  echo "       Looked at: ${URL}" >&2
  exit 1
}
curl -fsSL "${URL}" | tar -xz -C "${BIN}" --strip-components=1
chmod +x "${BIN}"/dockerd-rootless.sh "${BIN}"/dockerd-rootless-setuptool.sh "${BIN}"/rootlesskit
# The setuptool's self-check runs `<dir-of-setuptool>/docker version`, so it
# needs a `docker` next to itself; point it at the pacman CLI.
ln -sf "$(command -v docker)" "${BIN}/docker"

export PATH="${BIN}:${PATH}"

echo "==> [2/4] dockerd-rootless-setuptool.sh install"
dockerd-rootless-setuptool.sh install

echo "==> [3/4] enable the rootless daemon + select its CLI context"
systemctl --user enable --now docker.service
# The setuptool creates a `rootless` CLI context. Making it the default means
# `docker` — and every substrate script — targets the rootless daemon with no
# DOCKER_HOST env var: shell-agnostic, no ~/.bashrc / config.fish edits.
docker context use rootless

echo "==> [4/4] verify"
docker run --rm hello-world | grep -q "Hello from Docker" \
  && echo "    rootless Docker OK — engine ${DOCKER_VERSION}, CLI context 'rootless'"
