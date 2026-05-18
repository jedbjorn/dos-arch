#!/usr/bin/env python3
"""Per-shell scratch directories under the host shared folder.

Each shell gets `~/shared/<NN-shortname>/{redlines,review,repos,backups}` — its
own space inside the shared mount, for collaboration with FnB. The dir name is
the zero-padded `shell_id` + `shortname`: quote-safe (no spaces), sortable, and
stable — both halves are immutable for the life of the shell.

Created host-side. `bootstrap.py` (via `db_init`) makes them when it seeds
Forge + Sys-Admin; `run.py` re-ensures them at every launch (idempotent), so a
shell created via `POST /shells` — which runs inside the `dos-api` container,
with no access to `~/shared` — still has its tree before its first session.

The host `~/shared` is bind-mounted into each shell container at
`/root/shared`, i.e. the container's own `~/shared`. `ensure_shared_dirs`
operates on the host path; `shared_dir_container_path` returns the path as the
shell sees it from inside its container.
"""
from __future__ import annotations

import os
import pwd
from pathlib import Path

# Anchor the shared root to the running user's real home from the passwd
# database — NOT $HOME. `make bootstrap` / `make launch` run as the dos-arch
# service user; a stale $HOME (e.g. inherited from the operator's session)
# would otherwise send the tree to a directory the user cannot create, and
# mkdir(parents=True) would climb all the way to /home and fail there. The
# passwd entry is the OS truth and is immune to a misconfigured environment.
SHARED_ROOT = Path(pwd.getpwuid(os.getuid()).pw_dir) / "shared"
SUBDIRS = ("redlines", "review", "repos", "backups")
CONTAINER_SHARED = "~/shared"  # host ~/shared is mounted here inside shell containers


def shared_dir_name(shell_id: int, shortname: str) -> str:
    """Quote-safe, sortable dir name — zero-padded id + shortname, e.g. '02-forge'."""
    return f"{shell_id:02d}-{shortname}"


def ensure_shared_dirs(shell_id: int, shortname: str) -> Path:
    """Idempotently create the shell's scratch tree under the host shared
    folder. Returns the host path of the shell's root dir.

    The shared root itself (`SHARED_ROOT`) is laid down by
    `install/host-setup.sh`. If it is missing, fail loudly with a clear
    pointer rather than letting mkdir(parents=True) climb toward /home and
    surface a confusing permission error."""
    if not SHARED_ROOT.exists():
        raise FileNotFoundError(
            f"shared root {SHARED_ROOT} does not exist. Run "
            f"install/host-setup.sh (operator, sudo) before bootstrap/launch."
        )
    root = SHARED_ROOT / shared_dir_name(shell_id, shortname)
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def shared_dir_container_path(shell_id: int, shortname: str) -> str:
    """The shell's root dir as it appears INSIDE its container (`~/shared/...`)."""
    return f"{CONTAINER_SHARED}/{shared_dir_name(shell_id, shortname)}"
