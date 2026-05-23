"""The model registry — read surface for the browser-chat model-switch dropdown."""
from fastapi import APIRouter, Depends

from api.common.db import get_db

router = APIRouter(tags=["models"])


@router.get("/models", summary="List active models for the model-switch dropdown")
def list_models(con = Depends(get_db)):
    # supports_tools=1 only — dos-arch is a tool-driven substrate; a model
    # whose Ollama template lacks the `tools` capability 400s every turn
    # (and the dispatcher swallows it as a generic "overloaded"). Kept off
    # the picker entirely rather than surfaced and broken (see migration 034).
    rows = con.execute(
        "SELECT model_id, name, display_name, provider, tool_dialect, context_window "
        "FROM models WHERE status='active' AND supports_tools=1 "
        "ORDER BY provider, model_id"
    ).fetchall()
    return [dict(r) for r in rows]
