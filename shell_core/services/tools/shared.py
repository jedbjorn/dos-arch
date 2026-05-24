"""shared.py — host↔container shared-folder inspection handler.

Mirrors `shell_core/scripts/shared_dirs.py` for path resolution — kept in
sync by convention (the directory naming is one zero-padded id + shortname,
the host root is `~/dos-arch-shared/`). Both modules use the passwd-anchored
home, immune to a stale $HOME in the pm2 environment.

Returns JSON (not prose) — matches every other tool in the catalogue.
Smaller local models (observed: gemma4:e4b) reliably emit an empty post-tool
reply when the tool result is multi-line prose with non-ASCII glyphs;
structured JSON re-prompts them as "you just got back data, now answer"
where prose reads like "the assistant already answered" to whatever the
Ollama template renders. See chat msg 264/265 for the original trace."""
from __future__ import annotations

import json
import os
import pwd
from pathlib import Path

from .base import ToolError, ToolResult, require

# Mirror of shared_dirs.SHARED_ROOT / shared_dir_name(). Inlined rather than
# imported so this package stays self-contained (scripts/ is not on the
# dispatcher's sys.path; see services/__init__.py).
_SHARED_ROOT = Path(pwd.getpwuid(os.getuid()).pw_dir) / "dos-arch-shared"
_SUBDIRS = ("redlines", "review", "repos", "backups")


def _summarize(subdir: Path) -> dict:
    """{count, latest} for a subdir. `latest` is the most-recently-modified
    entry's filename, or null when the subdir is empty or missing."""
    if not subdir.is_dir():
        return {"count": 0, "latest": None, "missing": True}
    entries = sorted(subdir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "count": len(entries),
        "latest": entries[0].name if entries else None,
    }


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

    payload = {
        "path": str(root),
        "subdirs": {sub: _summarize(root / sub) for sub in _SUBDIRS},
    }
    return ToolResult(
        content=json.dumps(payload),
        meta={"path": str(root), "subdirs": list(_SUBDIRS)},
    )
