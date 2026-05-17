"""User picker + the authenticated user's recent-logs endpoint."""
from fastapi import APIRouter, HTTPException, Request, Depends

from api.common.db import get_db

router = APIRouter(tags=["users"])


@router.get("/me/recent-logs", summary="Get the authenticated user's last 10 API call logs")
def me_recent_logs(request: Request, con = Depends(get_db)):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    rows = con.execute(
        "SELECT log_id, method, path, status_code, duration_ms, timestamp FROM app_ui_logs WHERE user_id=? ORDER BY log_id DESC LIMIT 10",
        (user_id,)
    ).fetchall()
    return {"logs": [dict(r) for r in rows]}


@router.get("/users", summary="Search users by username/email — picker without email column (BR-137)")
def search_users(request: Request, q: str = "", con = Depends(get_db)):
    # BR-137: picker stays callable by everyone (mention typeahead, shell
    # assignment) but drops the email column from the response. Pickers only
    # render display_name + initials; email enumeration via /users?q= closes.
    # The full directory (with email) lives at /admin/users behind admin gate.
    if q:
        pattern = f"%{q}%"
        rows = con.execute(
            "SELECT user_id, username, initials FROM users WHERE is_active=1 AND (username LIKE ? OR email LIKE ?) ORDER BY username",
            (pattern, pattern)
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT user_id, username, initials FROM users WHERE is_active=1 ORDER BY username"
        ).fetchall()
    return [dict(r) for r in rows]
