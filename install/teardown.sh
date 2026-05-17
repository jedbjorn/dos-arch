#!/usr/bin/env bash
# teardown.sh — tear the rootless-Docker substrate back down for a clean,
# from-scratch rebuild. The inverse of rootless-setup.sh + build-image.sh +
# broker-up.sh.
#
# Run AS the dos-arch user, in a machinectl session:
#   sudo machinectl shell dos-arch@
#   ./install/teardown.sh        # (or  ~/setup/install/teardown.sh)
#
# Removes everything the dos-arch user owns:
#   - all containers, images, networks, volumes (docker system prune)
#   - rootless Docker itself — daemon + user systemd unit (via the setuptool)
#
# The dos-arch HOME (~/bin, ~/.local/share/docker, ~/.config, ~/setup, the
# ~/.bashrc env lines) is removed wholesale by the `userdel -r` in the sudo
# block printed at the end — no need to pick it apart here.
#
# Does NOT touch the host: the dos-arch user, linger, and pacman packages
# are host-level; the printed sudo block covers them.
#
# Idempotent — safe on a partial or already-removed install.
set -uo pipefail   # deliberately NOT -e: continue past already-absent items

if [[ ${EUID} -eq 0 ]]; then
  echo "ERROR: run as the dos-arch service user, not root." >&2
  exit 1
fi

BIN="${HOME}/bin"
export PATH="${BIN}:${PATH}"
[[ -n "${DOCKER_HOST:-}" ]] || export DOCKER_HOST="unix:///run/user/$(id -u)/docker.sock"

echo "==> [1/3] prune containers / images / networks / volumes"
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  docker system prune -af --volumes || true
  echo "    docker pruned"
else
  echo "    docker daemon not reachable — nothing to prune (skipped)"
fi

echo "==> [2/3] uninstall rootless Docker (daemon + user systemd unit)"
systemctl --user stop docker.service 2>/dev/null || true
if command -v dockerd-rootless-setuptool.sh >/dev/null; then
  dockerd-rootless-setuptool.sh uninstall -f || true
  echo "    rootless Docker uninstalled"
else
  echo "    dockerd-rootless-setuptool.sh not on PATH — skipped"
  echo "    (the userdel -r below removes ~/bin + all rootless state anyway)"
fi

echo "==> [3/3] remaining: host-level removal (needs sudo)"
cat <<'SUDO'

    The dos-arch user, its home, linger, and packages are host-level.
    Exit this session, then as a sudo user run:

      sudo loginctl disable-linger dos-arch
      sudo loginctl terminate-user dos-arch   # kill its sessions + systemd --user manager
      sudo userdel -r dos-arch                # removes /home/dos-arch wholesale
      sudo sed -i '/^dos-arch:/d' /etc/subuid /etc/subgid

    (disable-linger only stops the manager auto-starting; terminate-user
    stops the one already running, so userdel is not blocked.)

    Optional — only if Docker is not used by anything else on this host:

      sudo pacman -Rns docker docker-buildx slirp4netns fuse-overlayfs

    To REBUILD, stop here — the host is clean — and start at Phase 0:
      sudo ./install/host-setup.sh

    For a COMPLETE removal, also clear the operator-side leftovers that
    this script never touches — the repo clone (incl. .env, which holds
    real secrets), the launch-dos-arch shortcut, any sudoers drop-in, and
    the dos-arch traverse ACL on your home. See "Teardown" in
    install/README.md for the exact commands.
SUDO
echo "==> dos-arch-side teardown complete."
