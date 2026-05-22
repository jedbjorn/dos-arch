"""git.py — git handlers (spec §07.3).

subprocess wrapping the git binary — git's CLI is identical on every
platform, so there is nothing to normalize (spec §06.1). Every handler takes
`cwd`, the repository working directory. A non-zero git exit becomes a
`git_error` ToolError carrying git's own stderr."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .base import ToolError, ToolResult, require

_TIMEOUT = 120   # seconds — pull / push can be slow


def _resolve_cwd(params):
    """(cwd_str, error) — validate the repo working-dir param."""
    if (e := require(params, "cwd")):
        return None, e
    cwd = Path(params["cwd"]).expanduser()
    if not cwd.is_dir():
        return None, ToolError("not_found", f"cwd is not a directory: {cwd}")
    return str(cwd), None


def _capture(cwd, *args):
    """Run `git -C cwd <args>`. Returns (True, CompletedProcess) or
    (False, ToolError) — the latter for git-absent or a timeout."""
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True,
                           text=True, timeout=_TIMEOUT)
    except FileNotFoundError:
        return False, ToolError("not_found", "git is not installed")
    except subprocess.TimeoutExpired:
        return False, ToolError("timeout", f"git {args[0]} exceeded {_TIMEOUT}s")
    return True, r


def _fail(r, verb):
    """A git_error ToolError from a non-zero result — stderr first, stdout
    as fallback (checkout / push write their progress to stderr)."""
    return ToolError("git_error", (r.stderr or r.stdout).strip() or f"git {verb} failed")


def handle_status(params):
    cwd, e = _resolve_cwd(params)
    if e:
        return e
    ok, r = _capture(cwd, "status", "--porcelain=v1", "--branch")
    if not ok:
        return r
    if r.returncode != 0:
        return _fail(r, "status")
    return ToolResult(content=r.stdout or "(clean)", meta={"cwd": cwd})


def handle_diff(params):
    cwd, e = _resolve_cwd(params)
    if e:
        return e
    args = ["diff"]
    if params.get("staged"):
        args.append("--staged")
    if params.get("path"):
        args += ["--", str(params["path"])]
    ok, r = _capture(cwd, *args)
    if not ok:
        return r
    if r.returncode != 0:
        return _fail(r, "diff")
    return ToolResult(content=r.stdout or "(no changes)", meta={"cwd": cwd})


def handle_log(params):
    cwd, e = _resolve_cwd(params)
    if e:
        return e
    try:
        n = int(params.get("n") or 10)
    except (TypeError, ValueError):
        return ToolError("bad_params", "n must be an integer")
    args = ["log", f"-n{n}", "--date=short", "--pretty=format:%h  %an  %ad  %s"]
    if params.get("path"):
        args += ["--", str(params["path"])]
    ok, r = _capture(cwd, *args)
    if not ok:
        return r
    if r.returncode != 0:
        return _fail(r, "log")
    return ToolResult(content=r.stdout or "(no commits)", meta={"cwd": cwd})


def handle_branch(params):
    cwd, e = _resolve_cwd(params)
    if e:
        return e
    ok, r = _capture(cwd, "branch", "--list")
    if not ok:
        return r
    if r.returncode != 0:
        return _fail(r, "branch")
    return ToolResult(content=r.stdout or "(no branches)", meta={"cwd": cwd})


def handle_commit(params):
    cwd, e = _resolve_cwd(params)
    if e:
        return e
    if (e := require(params, "message")):
        return e
    if params.get("stage_all"):
        ok, r = _capture(cwd, "add", "-A")
        if not ok:
            return r
        if r.returncode != 0:
            return _fail(r, "add")
    ok, r = _capture(cwd, "commit", "-m", params["message"])
    if not ok:
        return r
    if r.returncode != 0:
        if "nothing to commit" in (r.stdout + r.stderr):
            return ToolError("empty_commit", "nothing staged to commit")
        return _fail(r, "commit")
    return ToolResult(content=r.stdout.strip(), meta={"cwd": cwd})


def handle_checkout(params):
    cwd, e = _resolve_cwd(params)
    if e:
        return e
    if (e := require(params, "branch")):
        return e
    args = ["checkout"]
    if params.get("create"):
        args.append("-b")
    args.append(params["branch"])
    ok, r = _capture(cwd, *args)
    if not ok:
        return r
    if r.returncode != 0:
        return _fail(r, "checkout")
    return ToolResult(content=(r.stderr or r.stdout).strip() or f"on {params['branch']}",
                      meta={"cwd": cwd})


def handle_pull(params):
    cwd, e = _resolve_cwd(params)
    if e:
        return e
    # fast-forward only by default — a merge that cannot ff is surfaced, not
    # silently committed (spec §07.3).
    args = ["pull", "--rebase"] if params.get("rebase") else ["pull", "--ff-only"]
    ok, r = _capture(cwd, *args)
    if not ok:
        return r
    if r.returncode != 0:
        return _fail(r, "pull")
    return ToolResult(content=(r.stdout or r.stderr).strip(), meta={"cwd": cwd})


def handle_push(params):
    cwd, e = _resolve_cwd(params)
    if e:
        return e
    args = ["push"]
    if params.get("force"):
        args.append("--force-with-lease")   # safer than a bare --force
    ok, r = _capture(cwd, *args)
    if not ok:
        return r
    if r.returncode != 0:
        return _fail(r, "push")
    return ToolResult(content=(r.stderr or r.stdout).strip() or "pushed",
                      meta={"cwd": cwd})
