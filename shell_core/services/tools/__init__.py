"""shell_core.services.tools — local-AI tool handlers (spec §05–07).

dispatch_live.execute_tool() routes any tool call whose stored `handler` key
is not 'api' into run_tool() here. Each handler is plain Python — OS variance
lives inside pathlib / shutil / subprocess / psutil / httpx, not in this code
(spec §06). _REGISTRY maps each tool's `handler` key to its callable; the
keys match what migration 026 writes onto the tool rows.

A sibling of `providers/` — both are the dispatcher's runtime concern, so
both live under services/, resolved on sys.path[0] like the dispatcher's
own imports."""
from __future__ import annotations

from . import files, git, network, process
from .base import ToolError, ToolResult

# handler key (tools.handler column) -> handler callable.
_REGISTRY = {
    "file.read":     files.handle_read,
    "file.write":    files.handle_write,
    "file.edit":     files.handle_edit,
    "file.append":   files.handle_append,
    "file.list":     files.handle_list,
    "file.search":   files.handle_search,
    "file.find":     files.handle_find,
    "file.delete":   files.handle_delete,
    "file.move":     files.handle_move,
    "proc.exec":     process.handle_exec,
    "proc.exec_bg":  process.handle_exec_bg,
    "proc.check":    process.handle_proc_check,
    "proc.kill":     process.handle_proc_kill,
    "proc.list":     process.handle_proc_list,
    "git.status":    git.handle_status,
    "git.diff":      git.handle_diff,
    "git.log":       git.handle_log,
    "git.branch":    git.handle_branch,
    "git.commit":    git.handle_commit,
    "git.checkout":  git.handle_checkout,
    "git.pull":      git.handle_pull,
    "git.push":      git.handle_push,
    "net.http_get":  network.handle_http_get,
    "net.http_post": network.handle_http_post,
    "net.url_fetch": network.handle_url_fetch,
}


def run_tool(handler: str, params: dict) -> tuple[str, bool]:
    """Execute one handler-keyed tool call. Returns (text, is_error) — the
    contract dispatch_live.execute_tool() expects. A handler crash is caught
    here and returned as an error, never raised into the dispatcher loop."""
    fn = _REGISTRY.get(handler)
    if fn is None:
        return f"no_handler: no tool handler registered for '{handler}'", True
    try:
        result = fn(params or {})
    except Exception as e:   # defence in depth — handlers should not raise
        return f"handler_crash: {type(e).__name__}: {e}", True
    if isinstance(result, ToolError):
        return f"{result.code}: {result.message}", True
    if isinstance(result, ToolResult):
        return result.content, False
    return (f"handler_crash: handler returned {type(result).__name__}, "
            "not a ToolResult"), True


def registered_handlers() -> set[str]:
    """The set of handler keys this package serves — used by tests / a
    migration check to confirm every tool row's handler has an implementation."""
    return set(_REGISTRY)


__all__ = ["run_tool", "registered_handlers", "ToolResult", "ToolError"]
