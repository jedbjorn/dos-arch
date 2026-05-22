"""base.py — the tool-handler result contract.

Every handler in this package takes a validated parameter dict and returns
one of two structured outcomes — never a bare value, never a raised
exception (run_tool() in __init__.py catches anything that escapes anyway).
A short, stable error *code* the model can branch on beats an opaque
traceback (spec §06.2)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolResult:
    """A handler succeeded. `content` is the text the model reads back; `meta`
    carries structured detail (paths, counts, pids) for logging, not the
    model."""
    content: str
    meta: dict = field(default_factory=dict)


@dataclass
class ToolError:
    """A handler failed in a known way. `code` is a short, stable token the
    model can match on — not_found, not_a_file, permission_denied, timeout,
    bad_params, … — `message` is the human-readable detail."""
    code: str
    message: str


def require(params: dict, *keys: str) -> ToolError | None:
    """Return a ToolError if any named param is missing or an empty/blank
    string, else None. For keys where an empty string is a valid value
    (file content, a replacement string) the handler checks `is None`
    itself rather than calling this."""
    for k in keys:
        v = params.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            return ToolError("bad_params", f"missing required parameter: {k}")
    return None
