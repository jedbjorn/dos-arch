"""BR-052 family — sanitized 5xx responses.

Echoing exception text in error responses leaks file paths, SQL fragments, and
internal stack frames. This module provides a single helper that logs the full
exception server-side and returns a sanitized detail string with a short
request_id for forensic correlation.
"""
import sys
import traceback
import uuid
from typing import Optional


def _log_5xx(where: str, exc: Optional[BaseException] = None) -> str:
    rid = uuid.uuid4().hex[:12]
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        print(f"[5xx] request_id={rid} where={where}\n{tb}", file=sys.stderr, flush=True)
    else:
        print(f"[5xx] request_id={rid} where={where}", file=sys.stderr, flush=True)
    return rid


def safe_5xx_detail(
    where: str,
    exc: Optional[BaseException] = None,
    message: str = "Internal server error",
) -> str:
    """Log full exception detail server-side; return a client-safe detail string.

    The returned string is suitable for ``HTTPException(status, detail=...)`` —
    callers keep their existing status codes (500/502/503) and pass the
    sanitized message they want clients to see, plus an optional ``where``
    label that goes only to the server log.
    """
    rid = _log_5xx(where, exc)
    return f"{message} (request_id={rid})"
