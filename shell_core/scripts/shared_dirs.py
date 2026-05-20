#!/usr/bin/env python3
"""Per-shell scratch directories under the host shared folder.

Each shell gets `~/dos-arch-shared/<NN-shortname>/{redlines,review,repos,
backups}` — its own space inside the shared mount, for collaboration with FnB.
The dir name is the zero-padded `shell_id` + `shortname`: quote-safe (no
spaces), sortable, and stable — both halves are immutable for the life of the
shell.

Created host-side. `bootstrap.py` (via `db_init`) makes them when it seeds
Forge + Sys-Admin; `run.py` re-ensures them at every launch (idempotent), so a
shell created via `POST /shells` — which runs inside the `dos-api` container,
with no access to the shared folder — still has its tree before its first
session.

The host shared folder is bind-mounted into each shell container at
`/root/shared`, i.e. the container's own `~/shared`. `ensure_shared_dirs`
operates on the host path; `shared_dir_container_path` returns the path as the
shell sees it from inside its container.
"""
from __future__ import annotations

import os
import pwd
from pathlib import Path

# Host shared root. Anchored to the operator's real home from the passwd
# database rather than $HOME — passwd is the OS truth, immune to a stale or
# unset environment. The `dos-arch-` prefix keeps it distinct from any other
# substrate's shared folder on the same host; a hyphen (not a space) keeps the
# path quote-safe, matching the no-spaces rule the per-shell dir names follow.
SHARED_ROOT = Path(pwd.getpwuid(os.getuid()).pw_dir) / "dos-arch-shared"
SUBDIRS = ("redlines", "review", "repos", "backups")
CONTAINER_SHARED = "~/shared"  # host SHARED_ROOT is mounted here inside shell containers


def shared_dir_name(shell_id: int, shortname: str) -> str:
    """Quote-safe, sortable dir name — zero-padded id + shortname, e.g. '02-forge'."""
    return f"{shell_id:02d}-{shortname}"


def ensure_shared_dirs(shell_id: int, shortname: str) -> Path:
    """Idempotently create the shell's scratch tree under the host shared
    folder, creating the shared root itself if it does not yet exist. Single
    user owns the whole tree, so a plain mkdir is safe — no service-user
    ownership to arrange. Returns the host path of the shell's root dir."""
    SHARED_ROOT.mkdir(parents=True, exist_ok=True)
    root = SHARED_ROOT / shared_dir_name(shell_id, shortname)
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def shared_dir_container_path(shell_id: int, shortname: str) -> str:
    """The shell's root dir as it appears INSIDE its container (`~/shared/...`)."""
    return f"{CONTAINER_SHARED}/{shared_dir_name(shell_id, shortname)}"
