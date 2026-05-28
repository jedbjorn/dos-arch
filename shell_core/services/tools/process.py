"""process.py — process-execution handlers (spec §07.2).

subprocess runs commands; psutil introspects them — psutil normalizes the
ps/tasklist gap across platforms (spec §06). exec takes argv as a *list*,
never a shell string: there is no shell expansion, so a metacharacter in an
argument is a literal, not an injection (spec §06.3).

exec_bg deviates from the spec: it redirects the child's output to a log
file under /tmp rather than streaming into the shell_logs table. Handlers
stay DB-free by design — wiring background output into shell_logs is left
to a later pass."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import psutil

from .base import ToolError, ToolResult, require
from .shared import resolve_path

_DEFAULT_TIMEOUT = 30                       # seconds
_MAX_TIMEOUT     = 300                      # hard ceiling (spec §06.3)
_BG_LOG_DIR      = Path("/tmp/dos-exec-bg")  # exec_bg stdout/stderr sink
_MAX_PROCS       = 500                      # cap on proc_list rows


def _resolve_cwd(params):
    """(cwd_str, error) — default to the dispatcher's cwd, never `/`."""
    cwd = resolve_path(params.get("cwd") or os.getcwd())
    if not cwd.is_dir():
        return None, ToolError("not_found", f"cwd is not a directory: {cwd}")
    return str(cwd), None


def _check_argv(params):
    argv = params.get("argv")
    if (not isinstance(argv, list) or not argv
            or not all(isinstance(a, str) for a in argv)):
        return None, ToolError("bad_params", "argv must be a non-empty list of strings")
    return argv, None


def handle_exec(params):
    argv, e = _check_argv(params)
    if e:
        return e
    cwd, e = _resolve_cwd(params)
    if e:
        return e
    try:
        timeout = min(int(params.get("timeout") or _DEFAULT_TIMEOUT), _MAX_TIMEOUT)
    except (TypeError, ValueError):
        return ToolError("bad_params", "timeout must be an integer (seconds)")
    t0 = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout)
    except FileNotFoundError:
        return ToolError("not_found", f"command not found: {argv[0]}")
    except PermissionError as e:
        return ToolError("permission_denied", str(e))
    except subprocess.TimeoutExpired:
        return ToolError("timeout", f"command exceeded {timeout}s")
    dur = int((time.monotonic() - t0) * 1000)
    body = (f"exit_code: {proc.returncode}  duration_ms: {dur}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}")
    return ToolResult(content=body,
                      meta={"exit_code": proc.returncode, "duration_ms": dur})


def handle_exec_bg(params):
    argv, e = _check_argv(params)
    if e:
        return e
    cwd, e = _resolve_cwd(params)
    if e:
        return e
    _BG_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _BG_LOG_DIR / f"bg-{int(time.time() * 1000)}.log"
    try:
        log_fh = open(log_path, "w", encoding="utf-8")
    except OSError as e:
        return ToolError("io_error", f"cannot open background log: {e}")
    try:
        # start_new_session detaches the child from the dispatcher's process
        # group, so it survives a dispatcher restart; output redirects
        # straight to the log fd, so no drain thread has to outlive the call.
        proc = subprocess.Popen(argv, cwd=cwd, stdout=log_fh,
                                stderr=subprocess.STDOUT, start_new_session=True)
    except FileNotFoundError:
        return ToolError("not_found", f"command not found: {argv[0]}")
    except PermissionError as e:
        return ToolError("permission_denied", str(e))
    finally:
        log_fh.close()   # the child holds its own dup of the fd
    return ToolResult(content=f"started pid {proc.pid}  output: {log_path}",
                      meta={"pid": proc.pid, "log": str(log_path)})


def handle_proc_check(params):
    pid = params.get("pid")
    if not isinstance(pid, int):
        return ToolError("bad_params", "pid must be an integer")
    if not psutil.pid_exists(pid):
        return ToolResult(content=f"pid {pid}: not running",
                          meta={"pid": pid, "alive": False})
    try:
        info = psutil.Process(pid).as_dict(attrs=["status", "create_time", "name"])
    except psutil.NoSuchProcess:
        return ToolResult(content=f"pid {pid}: not running",
                          meta={"pid": pid, "alive": False})
    except psutil.AccessDenied:
        return ToolResult(content=f"pid {pid}: running (details not permitted)",
                          meta={"pid": pid, "alive": True})
    runtime = int(time.time() - (info.get("create_time") or time.time()))
    body = f"pid {pid} ({info.get('name')}): {info.get('status')}, runtime {runtime}s"
    return ToolResult(content=body,
                      meta={"pid": pid, "alive": True, "runtime_s": runtime})


def handle_proc_kill(params):
    pid = params.get("pid")
    if not isinstance(pid, int):
        return ToolError("bad_params", "pid must be an integer")
    sig = params.get("signal") or "SIGTERM"
    try:
        signum = signal.Signals[sig].value if isinstance(sig, str) else int(sig)
    except (KeyError, ValueError):
        return ToolError("bad_params", f"unknown signal: {sig}")
    if not psutil.pid_exists(pid):
        return ToolError("not_found", f"no process with pid {pid}")
    try:
        os.kill(pid, signum)
    except PermissionError:
        return ToolError("permission_denied", f"not permitted to signal pid {pid}")
    except ProcessLookupError:
        return ToolError("not_found", f"no process with pid {pid}")
    return ToolResult(content=f"sent {sig} to pid {pid}",
                      meta={"pid": pid, "signal": str(sig)})


def handle_proc_list(params):
    name_filter = params.get("name_filter")
    rows = []
    for p in psutil.process_iter(attrs=["pid", "name", "username"]):
        try:
            info = p.info
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        name = info.get("name") or ""
        if name_filter and name_filter.lower() not in name.lower():
            continue
        rows.append(f"{info.get('pid'):>8}  {(info.get('username') or '?'):<14}  {name}")
        if len(rows) >= _MAX_PROCS:
            rows.append(f"… (capped at {_MAX_PROCS})")
            break
    return ToolResult(content="\n".join(rows) or "(no matching processes)",
                      meta={"count": len(rows)})
