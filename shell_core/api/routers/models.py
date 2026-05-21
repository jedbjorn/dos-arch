"""The model registry — read surface for the browser-chat model-switch dropdown."""
from fastapi import APIRouter, Depends

from api.common.db import get_db

router = APIRouter(tags=["models"])


@router.get("/models", summary="List active models for the model-switch dropdown")
def list_models(con = Depends(get_db)):
    rows = con.execute(
        "SELECT model_id, name, display_name, provider, tool_dialect, context_window "
        "FROM models WHERE status='active' ORDER BY provider, model_id"
    ).fetchall()
    return [dict(r) for r in rows]
