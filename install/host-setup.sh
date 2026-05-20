#!/usr/bin/env bash
# host-setup.sh — Arch host bootstrap for the dos-arch substrate (sudo).
#
# Installs the system packages and prepares the operator for rootless Docker:
# ensures subuid/subgid ranges and enables linger so the operator's rootless
# Docker daemon survives logout.
#
#   sudo ./install/host-setup.sh
#
# Single-user model: rootless Docker, the substrate, and every container all
# run as the operator — the user who invoked sudo. There is NO dedicated
# service user. This is the only step that needs root; everything after runs
# as the operator with no sudo. Idempotent — safe to re-run. Pairs with
# rootless-setup.sh (run next, as the operator).
set -euo pipefail

RANGE=65536

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: run with sudo — installs packages and edits subuid/subgid." >&2
  exit 1
fi
command -v pacman >/dev/null || {
  echo "ERROR: pacman not found — this script targets Arch-based systems." >&2
  exit 1
}
OPERATOR="${SUDO_USER:-}"
if [[ -z "${OPERATOR}" ]] || ! id "${OPERATOR}" &>/dev/null; then
  echo "ERROR: cannot determine the operator — invoke via 'sudo', not as root." >&2
  exit 1
fi
echo "=== dos-arch host bootstrap ===  operator: ${OPERATOR}"

echo "==> [1/4] system packages (pacman)"
# git/base-devel : clone + make entry points    python  : runtime + venv
# nodejs/npm     : SvelteKit UI                  docker* : container sandbox
# slirp4netns/fuse-overlayfs : rootless Docker networking + storage fallback
# cronie         : cron daemon — runs the nightly catalogue sync
pacman -S --needed --noconfirm \
  git base-devel python nodejs npm cronie \
  docker docker-buildx slirp4netns fuse-overlayfs

echo "==> [2/4] pm2 (npm global — host process manager for the UI + dispatcher)"
if command -v pm2 >/dev/null; then
  echo "    pm2 present — skipping"
else
  npm install -g pm2
fi

echo "==> [3/4] enable the cron daemon (for the nightly catalogue sync)"
systemctl enable --now cronie
echo "    cronie enabled"

echo "==> [4/4] operator rootless prerequisites"
# subuid/subgid — rootless Docker maps container UIDs into this range.
if grep -q "^${OPERATOR}:" /etc/subuid && grep -q "^${OPERATOR}:" /etc/subgid; then
  echo "    subuid/subgid present: $(grep "^${OPERATOR}:" /etc/subuid)"
else
  # Start a fresh 65536-block above every existing allocation (min 100000).
  end=$(awk -F: '{ e=$2+$3; if (e>m) m=e } END { print m+0 }' /etc/subuid)
  start=$(( end > 100000 ? end : 100000 ))
  usermod --add-subuids "${start}-$((start + RANGE - 1))" \
          --add-subgids "${start}-$((start + RANGE - 1))" "${OPERATOR}"
  echo "    subuid/subgid added: ${start}-$((start + RANGE - 1))"
fi
# linger — keeps the operator's systemd --user manager (and the rootless
# Docker daemon) alive after logout, so the substrate runs unattended.
loginctl enable-linger "${OPERATOR}"
echo "    linger enabled for ${OPERATOR}"

cat <<EOF

Host bootstrap done. Everything from here runs AS THE OPERATOR — no sudo:

  ./install/rootless-setup.sh    install + start rootless Docker

setup.sh runs that and the rest end-to-end — see install/README.md.

Note: the rootful Docker daemon (docker.service) is left untouched. The
substrate uses a rootless daemon under its own CLI context; rootless-setup.sh
selects it. If you want rootful Docker off, disable it yourself.
EOF
