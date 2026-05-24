"""shared.py — host↔container shared-folder inspection handler.

Mirrors `shell_core/scripts/shared_dirs.py` for path resolution — kept in
sync by convention (the directory naming is one zero-padded id + shortname,
the host root is `~/dos-arch-shared/`). Both modules use the passwd-anchored
home, immune to a stale $HOME in the pm2 environment."""
from __future__ import annotations

import os
import pwd
from pathlib import Path

from .base import ToolError, ToolResult, require

# Mirror of shared_dirs.SHARED_ROOT / shared_dir_name(). Inlined rather than
# imported so this package stays self-contained (scripts/ is not on the
# dispatcher's sys.path; see services/__init__.py).
_SHARED_ROOT = Path(pwd.getpwuid(os.getuid()).pw_dir) / "dos-arch-shared"
_SUBDIRS = ("redlines", "review", "repos", "backups")


def _summarize(subdir: Path) -> str:
    """One-line listing for a subdir: count + most-recent entry name."""
    if not subdir.is_dir():
        return "(missing)"
    entries = sorted(subdir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    if not entries:
        return "empty"
    return f"{len(entries)} entries; latest: {entries[0].name}"


def handle_inspect(params: dict):
    if (e := require(params, "shortname")):
        return e
    shell_id = params.get("shell_id")
    if not isinstance(shell_id, int):
        return ToolError("bad_params", "shell_id must be an integer")
    shortname = params["shortname"]

    root = _SHARED_ROOT / f"{shell_id:02d}-{shortname}"
    if not root.is_dir():
        return ToolError(
            "not_found",
            f"shared dir does not exist: {root} "
            f"(expected on first `make launch` of this shell)",
        )

    lines = [f"path: {root}"]
    for sub in _SUBDIRS:
        lines.append(f"  {sub}/ — {_summarize(root / sub)}")
    return ToolResult(
        content="\n".join(lines),
        meta={"path": str(root), "subdirs": list(_SUBDIRS)},
    )
