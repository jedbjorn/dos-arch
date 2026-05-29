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
SHARED_ROOT = Path(pwd.getpwuid(os.getuid()).pw_dir) / "dos-arch-shared"
_SUBDIRS = ("redlines", "review", "repos", "backups")

# Legacy path prefixes the model still emits from the container era, when
# host SHARED_ROOT was bind-mounted into the shell container at ~/shared
# (HOME=/root). The dispatcher now runs host-side, so expanduser() would
# resolve ~/shared to /home/<user>/shared — a separate tree from SHARED_ROOT.
# resolve_path() rebinds these prefixes to SHARED_ROOT before expansion.
_LEGACY_SHARED_PREFIXES = ("~/shared", "/root/shared")


def resolve_path(p) -> Path:
    """Tool-handler path normalizer. Rebinds legacy ~/shared/* paths to
    SHARED_ROOT, then expanduser()s the result. Use everywhere a tool
    handler accepts a path argument from the model."""
    s = str(p)
    for prefix in _LEGACY_SHARED_PREFIXES:
        if s == prefix:
            return SHARED_ROOT
        if s.startswith(prefix + "/"):
            return SHARED_ROOT / s[len(prefix) + 1:]
    return Path(s).expanduser()


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

    root = SHARED_ROOT / f"{shell_id:02d}-{shortname}"
    if not root.is_dir():
        return ToolError(
            "not_found",
            f"shared dir does not exist: {root} "
            f"(shells get their tree at creation — this one predates that fix "
            f"or was made out-of-band)",
        )

    payload = {
        "path": str(root),
        "subdirs": {sub: _summarize(root / sub) for sub in _SUBDIRS},
    }
    return ToolResult(
        content=json.dumps(payload),
        meta={"path": str(root), "subdirs": list(_SUBDIRS)},
    )
