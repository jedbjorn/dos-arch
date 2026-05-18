#!/usr/bin/env bash
# host-setup.sh — Arch host bootstrap for the dos-arch substrate (sudo).
#
# Creates the unprivileged `dos-arch` service user, installs the Docker
# packages, leaves the rootful daemon disabled, enables linger so the
# user's rootless daemon survives logout, and stages the dos-arch-side
# setup files into /home/dos-arch/setup.
#
#   sudo ./install/host-setup.sh
#
# Idempotent — safe to re-run. Pairs with rootless-setup.sh (run AS dos-arch).
set -euo pipefail

SERVICE_USER="dos-arch"
SERVICE_HOME="/home/${SERVICE_USER}"
RANGE=65536

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: run with sudo — creates a user and installs packages." >&2
  exit 1
fi
command -v pacman >/dev/null || {
  echo "ERROR: pacman not found — this script targets Arch-based systems." >&2
  exit 1
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> [1/7] service user: ${SERVICE_USER}"
if id "${SERVICE_USER}" &>/dev/null; then
  echo "    exists — skipping"
else
  useradd -m -d "${SERVICE_HOME}" -s /bin/bash "${SERVICE_USER}"
  echo "    created"
fi

echo "==> [2/7] subuid / subgid ranges"
if grep -q "^${SERVICE_USER}:" /etc/subuid && grep -q "^${SERVICE_USER}:" /etc/subgid; then
  echo "    present: $(grep "^${SERVICE_USER}:" /etc/subuid)"
else
  # Start a fresh 65536-block above every existing allocation (min 100000).
  end=$(awk -F: '{ e=$2+$3; if (e>m) m=e } END { print m+0 }' /etc/subuid)
  start=$(( end > 100000 ? end : 100000 ))
  usermod --add-subuids "${start}-$((start + RANGE - 1))" \
          --add-subgids "${start}-$((start + RANGE - 1))" "${SERVICE_USER}"
  echo "    added ${start}-$((start + RANGE - 1))"
fi

echo "==> [3/7] Docker packages (pacman)"
# fuse-overlayfs is the storage fallback for kernels < 5.13; harmless on newer.
# acl provides setfacl — used in step 6 to bridge the operator into ~/shared.
pacman -S --needed --noconfirm docker docker-buildx slirp4netns fuse-overlayfs acl

echo "==> [4/7] disable the rootful daemon (substrate runs rootless only)"
systemctl disable --now docker.service docker.socket 2>/dev/null || true
echo "    docker.service / docker.socket disabled"

echo "==> [5/7] enable linger for ${SERVICE_USER}"
loginctl enable-linger "${SERVICE_USER}"

echo "==> [6/7] shared runtime directory"
# Host-side shared root, owned by the service user and bind-mounted into every
# shell container. Runtime state — never in the repo. Only the ROOT is created
# here; the per-shell subdirs (<NN-shortname>/{redlines,review,repos,backups})
# are laid down later by `make bootstrap` / run.py, keyed by shell_id.
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${SERVICE_HOME}/shared"
echo "    ${SERVICE_HOME}/shared"

# FnB bridge: let the operator (the human who invoked sudo) read AND write the
# shared tree, so redlines and handoffs flow both ways while ownership stays
# cleanly with the service user. The default ACL (-d) makes files the
# substrate creates under it later inherit the grant. Mirror of the clone-ACL
# grant in install/README.md step 3, in the opposite direction.
if [[ -n "${SUDO_USER:-}" ]] && id "${SUDO_USER}" &>/dev/null; then
  setfacl -m       "u:${SUDO_USER}:x"   "${SERVICE_HOME}"
  setfacl -R -m    "u:${SUDO_USER}:rwX" "${SERVICE_HOME}/shared"
  setfacl -R -d -m "u:${SUDO_USER}:rwX" "${SERVICE_HOME}/shared"
  echo "    operator '${SUDO_USER}' granted rw on ${SERVICE_HOME}/shared"
else
  echo "    WARNING: \$SUDO_USER unset — skipped operator ACL grant."
  echo "             Grant manually: setfacl -R -m u:<operator>:rwX ${SERVICE_HOME}/shared"
fi

echo "==> [7/7] stage setup files into ${SERVICE_HOME}/setup"
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${SERVICE_HOME}/setup"
cp -r "${REPO_ROOT}/install" "${REPO_ROOT}/docker" "${SERVICE_HOME}/setup/"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${SERVICE_HOME}/setup"

cat <<EOF

Host bootstrap done. Remaining steps — full detail in install/README.md:

  2. Rootless Docker — in a real ${SERVICE_USER} session:
       sudo machinectl shell ${SERVICE_USER}@
       cd ~/setup && ./install/rootless-setup.sh

  3. Create .env (as the operator, in your repo clone) and grant
     ${SERVICE_USER} read access — see README step 3.

  4. Build images + start the broker. build-image.sh / broker-up.sh need
     the FULL repo, so run them from your clone, NOT ~/setup:
       sudo machinectl shell ${SERVICE_USER}@
       cd /path/to/dos-arch && ./install/build-image.sh && ./install/broker-up.sh
EOF
