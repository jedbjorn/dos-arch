#!/usr/bin/env bash
# rootless-setup.sh — install + start rootless Docker for the current user.
#
# Run AS the dos-arch service user, inside a real user session — use
# `machinectl`, NOT `sudo -iu`: rootless Docker's `systemctl --user` needs a
# user systemd manager and XDG_RUNTIME_DIR, which only a login session gives.
#
#   sudo machinectl shell dos-arch@      # then, inside:
#   ./install/rootless-setup.sh
#
# The Arch/CachyOS `docker` package ships dockerd/containerd but no rootless
# wrapper scripts, so this fetches docker-ce's version-matched rootless-extras
# (the wrapper scripts + rootlesskit) into ~/bin. dockerd/containerd stay
# pacman-managed and auto-update. Idempotent — safe to re-run.
set -euo pipefail

if [[ ${EUID} -eq 0 ]]; then
  echo "ERROR: run as the unprivileged service user, not root." >&2
  exit 1
fi
if [[ -z "${XDG_RUNTIME_DIR:-}" ]]; then
  echo "ERROR: no user session (XDG_RUNTIME_DIR unset)." >&2
  echo "       Enter one with: sudo machinectl shell dos-arch@" >&2
  exit 1
fi
command -v docker >/dev/null || {
  echo "ERROR: docker not installed — run host-setup.sh first." >&2
  exit 1
}

BIN="${HOME}/bin"
SOCK="unix:///run/user/$(id -u)/docker.sock"
ARCH="$(uname -m)"

DOCKER_VERSION="$(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)"
[[ -n "${DOCKER_VERSION}" ]] || { echo "ERROR: cannot parse docker version." >&2; exit 1; }
echo "==> docker engine ${DOCKER_VERSION} (${ARCH})"

echo "==> [1/5] fetch rootless-extras into ${BIN}"
mkdir -p "${BIN}"
URL="https://download.docker.com/linux/static/stable/${ARCH}/docker-rootless-extras-${DOCKER_VERSION}.tgz"
curl -fsI "${URL}" >/dev/null || {
  echo "ERROR: no rootless-extras tarball for docker ${DOCKER_VERSION} (${ARCH})." >&2
  echo "       Looked at: ${URL}" >&2
  exit 1
}
curl -fsSL "${URL}" | tar -xz -C "${BIN}" --strip-components=1
chmod +x "${BIN}"/dockerd-rootless.sh "${BIN}"/dockerd-rootless-setuptool.sh "${BIN}"/rootlesskit
# The setuptool's final self-check runs `<dir-of-setuptool>/docker version`,
# so it needs a `docker` next to itself; point it at the pacman CLI.
ln -sf "$(command -v docker)" "${BIN}/docker"

export PATH="${BIN}:${PATH}"
export DOCKER_HOST="${SOCK}"

echo "==> [2/5] dockerd-rootless-setuptool.sh install"
dockerd-rootless-setuptool.sh install

echo "==> [3/5] persist env in ~/.bashrc"
touch ~/.bashrc
grep -qxF "export PATH=${BIN}:\$PATH" ~/.bashrc \
  || echo "export PATH=${BIN}:\$PATH" >> ~/.bashrc
grep -qxF "export DOCKER_HOST=${SOCK}" ~/.bashrc \
  || echo "export DOCKER_HOST=${SOCK}" >> ~/.bashrc

echo "==> [4/5] enable + start docker.service (user)"
systemctl --user enable --now docker.service

echo "==> [5/5] verify"
docker run --rm hello-world | grep -q "Hello from Docker" \
  && echo "    rootless Docker OK — version ${DOCKER_VERSION}, socket ${SOCK}"
