#!/usr/bin/env bash
# teardown.sh — tear the dos-arch substrate back down. Run as the operator.
#
#   ./install/teardown.sh
#
# The inverse of setup.sh: stops the pm2 services, removes every container
# and image, uninstalls rootless Docker, and clears its data directory.
#
# Does NOT touch: pacman packages, the operator's subuid/subgid + linger, the
# repo clone, or ~/.config/dos-arch/.env. Re-run setup.sh to rebuild. For a
# from-scratch (fresh-DB) rebuild, see the note printed at the end.
#
# Idempotent — safe on a partial or already-removed install.
set -uo pipefail   # deliberately NOT -e: continue past already-absent items

BIN="${HOME}/bin"
export PATH="${BIN}:${PATH}"

echo "==> [1/5] stop pm2 services (UI + dispatcher)"
if command -v pm2 >/dev/null; then
  pm2 delete ecosystem.config.cjs >/dev/null 2>&1 \
    || pm2 delete dosarch-ui dosarch-dispatch >/dev/null 2>&1 || true
  echo "    pm2 services removed"
else
  echo "    pm2 not installed — skipped"
fi

echo "==> [2/5] remove all containers (prune does NOT stop running ones)"
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  ids="$(docker ps -aq)"
  if [[ -n "${ids}" ]]; then
    docker rm -f ${ids} >/dev/null 2>&1 || true
  fi
  echo "    containers removed"
else
  echo "    docker daemon not reachable — skipped"
fi

echo "==> [3/5] prune images / networks / volumes / build cache"
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  docker system prune -af --volumes >/dev/null 2>&1 || true
  echo "    docker pruned"
else
  echo "    docker daemon not reachable — skipped"
fi

echo "==> [4/5] uninstall rootless Docker (daemon + user systemd unit)"
systemctl --user stop docker.service 2>/dev/null || true
if command -v dockerd-rootless-setuptool.sh >/dev/null; then
  dockerd-rootless-setuptool.sh uninstall -f || true
  echo "    rootless Docker uninstalled"
else
  echo "    dockerd-rootless-setuptool.sh not on PATH — skipped"
fi

echo "==> [5/5] clear the rootless Docker data directory"
# The uninstall tool deliberately leaves engine data behind. Its files are
# owned by mapped sub-UIDs, so `rootlesskit rm` (which runs inside the user
# namespace) is needed; plain rm is the fallback.
DATA="${HOME}/.local/share/docker"
if [[ -d "${DATA}" ]]; then
  if [[ -x "${BIN}/rootlesskit" ]]; then
    "${BIN}/rootlesskit" rm -rf "${DATA}" 2>/dev/null || rm -rf "${DATA}" 2>/dev/null || true
  else
    rm -rf "${DATA}" 2>/dev/null || true
  fi
  [[ -d "${DATA}" ]] && echo "    WARNING: ${DATA} not fully removed" || echo "    ${DATA} removed"
else
  echo "    ${DATA} absent — nothing to clear"
fi

cat <<'EOF'

==> substrate teardown complete.

Kept: pacman packages, the operator's subuid/subgid + linger, the repo clone,
and ~/.config/dos-arch/.env. Re-run ./install/setup.sh to rebuild.

For a FROM-SCRATCH rebuild (fresh DB), also wipe every build artifact — the
DB, .venv, node_modules, .svelte-kit, rendered shells. From the repo root,
the reliable one-liner (catches everything git ignores — no path list to
keep in sync):

    git clean -xfd
EOF
