"""files.py — file-operation handlers (spec §07.1).

pathlib / shutil / re only — no shell-out to `find` or `grep`, so BSD/GNU
and POSIX/Windows variance stays inside the stdlib (spec §06). Paths are
expanduser()'d so a `~/` argument works regardless of the caller's cwd.

v0.2 scope: a handler operates on whatever path it is given. A per-shell
sandboxed root is a v0.3 concern — there is no schema for it yet (spec
§06.3 defers broader sandboxing)."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .base import ToolError, ToolResult, require

_MAX_SEARCH_HITS = 200    # cap on file_search matches returned to the model
_MAX_ENTRIES     = 1000   # cap on file_list / file_find entries


def handle_read(params):
    if (e := require(params, "path")):
        return e
    path = Path(params["path"]).expanduser()
    if not path.exists():
        return ToolError("not_found", f"path does not exist: {path}")
    if not path.is_file():
        return ToolError("not_a_file", f"path is not a file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ToolError("binary_file", f"file is not utf-8 text: {path}")
    except PermissionError as e:
        return ToolError("permission_denied", str(e))
    lines = params.get("lines")
    if lines:
        try:
            start, end = int(lines[0]), int(lines[1])
        except (TypeError, ValueError, IndexError):
            return ToolError("bad_params", "lines must be [start, end] integers")
        text = "\n".join(text.splitlines()[start - 1:end])
    return ToolResult(content=text, meta={"path": str(path), "chars": len(text)})


def handle_write(params):
    if (e := require(params, "path")):
        return e
    content = params.get("content")
    if content is None:
        return ToolError("bad_params", "missing required parameter: content")
    path = Path(params["path"]).expanduser()
    if path.exists():
        return ToolError("exists", f"path already exists — use file_edit: {path}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        n = path.write_text(content, encoding="utf-8")
    except PermissionError as e:
        return ToolError("permission_denied", str(e))
    return ToolResult(content=f"wrote {n} chars to {path}",
                      meta={"path": str(path), "chars": n})


def handle_edit(params):
    if (e := require(params, "path", "old_str")):
        return e
    new_str = params.get("new_str")
    if new_str is None:
        return ToolError("bad_params", "missing required parameter: new_str")
    path = Path(params["path"]).expanduser()
    if not path.is_file():
        return ToolError("not_found", f"not a file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ToolError("binary_file", f"file is not utf-8 text: {path}")
    except PermissionError as e:
        return ToolError("permission_denied", str(e))
    count = text.count(params["old_str"])
    if count == 0:
        return ToolError("no_match", "old_str not found in file")
    if count > 1:
        return ToolError("not_unique", f"old_str matches {count} times — make it unique")
    path.write_text(text.replace(params["old_str"], new_str, 1), encoding="utf-8")
    return ToolResult(content=f"edited {path}", meta={"path": str(path)})


def handle_append(params):
    if (e := require(params, "path")):
        return e
    content = params.get("content")
    if content is None:
        return ToolError("bad_params", "missing required parameter: content")
    path = Path(params["path"]).expanduser()
    try:
        with path.open("a", encoding="utf-8") as fh:
            n = fh.write(content)
    except FileNotFoundError:
        return ToolError("not_found", f"no such directory for: {path}")
    except IsADirectoryError:
        return ToolError("not_a_file", f"path is a directory: {path}")
    except PermissionError as e:
        return ToolError("permission_denied", str(e))
    return ToolResult(content=f"appended {n} chars to {path}",
                      meta={"path": str(path), "chars": n})


def handle_list(params):
    if (e := require(params, "path")):
        return e
    path = Path(params["path"]).expanduser()
    if not path.is_dir():
        return ToolError("not_found", f"not a directory: {path}")
    walk = path.rglob("*") if params.get("recursive") else path.iterdir()
    entries = []
    for p in sorted(walk):
        if len(entries) >= _MAX_ENTRIES:
            entries.append(f"… (capped at {_MAX_ENTRIES})")
            break
        kind = "dir " if p.is_dir() else "file"
        size = p.stat().st_size if p.is_file() else ""
        entries.append(f"{kind}  {size:>10}  {p}")
    return ToolResult(content="\n".join(entries) or "(empty)",
                      meta={"path": str(path), "count": len(entries)})


def handle_search(params):
    if (e := require(params, "pattern")):
        return e
    root = Path(params.get("path") or ".").expanduser()
    if not root.exists():
        return ToolError("not_found", f"path does not exist: {root}")
    use_regex = bool(params.get("regex"))
    matcher = None
    if use_regex:
        try:
            matcher = re.compile(params["pattern"])
        except re.error as ex:
            return ToolError("bad_params", f"invalid regex: {ex}")
    targets = [root] if root.is_file() else root.rglob("*")
    hits, capped = [], False
    for f in targets:
        if not f.is_file():
            continue
        try:
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if (matcher.search(line) if matcher else params["pattern"] in line):
                    hits.append(f"{f}:{n}: {line.strip()[:200]}")
                    if len(hits) >= _MAX_SEARCH_HITS:
                        capped = True
                        break
        except (UnicodeDecodeError, PermissionError, OSError):
            continue
        if capped:
            break
    if capped:
        hits.append(f"… (capped at {_MAX_SEARCH_HITS} matches)")
    return ToolResult(content="\n".join(hits) or "(no matches)",
                      meta={"matches": len(hits)})


def handle_find(params):
    if (e := require(params, "name_pattern")):
        return e
    root = Path(params.get("path") or ".").expanduser()
    if not root.is_dir():
        return ToolError("not_found", f"not a directory: {root}")
    matches = []
    for p in sorted(root.rglob(params["name_pattern"])):
        if len(matches) >= _MAX_ENTRIES:
            matches.append(f"… (capped at {_MAX_ENTRIES})")
            break
        matches.append(str(p))
    return ToolResult(content="\n".join(matches) or "(no matches)",
                      meta={"matches": len(matches)})


def handle_delete(params):
    if (e := require(params, "path")):
        return e
    path = Path(params["path"]).expanduser()
    if not path.exists():
        return ToolError("not_found", f"path does not exist: {path}")
    if path.is_dir():
        return ToolError("is_a_directory", f"refusing to delete a directory: {path}")
    try:
        path.unlink()
    except PermissionError as e:
        return ToolError("permission_denied", str(e))
    return ToolResult(content=f"deleted {path}", meta={"path": str(path)})


def handle_move(params):
    if (e := require(params, "src", "dst")):
        return e
    src = Path(params["src"]).expanduser()
    dst = Path(params["dst"]).expanduser()
    if not src.exists():
        return ToolError("not_found", f"source does not exist: {src}")
    if dst.exists():
        return ToolError("exists", f"destination already exists: {dst}")
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except PermissionError as e:
        return ToolError("permission_denied", str(e))
    return ToolResult(content=f"moved {src} -> {dst}",
                      meta={"src": str(src), "dst": str(dst)})
