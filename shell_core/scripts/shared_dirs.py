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

from pathlib import Path

SHARED_ROOT = Path.home() / "shared"
SUBDIRS = ("redlines", "review", "repos", "backups")
CONTAINER_SHARED = "~/shared"  # host ~/shared is mounted here inside shell containers


def shared_dir_name(shell_id: int, shortname: str) -> str:
    """Quote-safe, sortable dir name — zero-padded id + shortname, e.g. '02-forge'."""
    return f"{shell_id:02d}-{shortname}"


def ensure_shared_dirs(shell_id: int, shortname: str) -> Path:
    """Idempotently create the shell's scratch tree under the host shared
    folder. Returns the host path of the shell's root dir."""
    root = SHARED_ROOT / shared_dir_name(shell_id, shortname)
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def shared_dir_container_path(shell_id: int, shortname: str) -> str:
    """The shell's root dir as it appears INSIDE its container (`~/shared/...`)."""
    return f"{CONTAINER_SHARED}/{shared_dir_name(shell_id, shortname)}"
