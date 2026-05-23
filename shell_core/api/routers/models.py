"""The model registry — read surface for the browser-chat model-switch dropdown."""
from fastapi import APIRouter, Depends, HTTPException

from api.common.db import get_db

router = APIRouter(tags=["models"])

# Minimum native context a model needs to carry the substrate boot prompt
# (~6k) plus reasonable conversation room. Below this, even tool-capable
# templates burn the entire window on the system prefix and leave nothing
# for the chat. Models under the threshold route to the agent surface.
_SUBSTRATE_CONTEXT_MIN = 20480


@router.get("/models", summary="List active models for the model-switch dropdown")
def list_models(con = Depends(get_db)):
    # Picker = substrate-capable only: tools + system-with-tools acceptance
    # + enough context to actually carry the boot prompt. NULL classifications
    # are excluded (they mean "not yet probed by modelsync" — they reappear
    # once the classifier writes a 1). See migrations 034 and 035.
    rows = con.execute(
        """
        SELECT model_id, name, display_name, provider, tool_dialect, context_window
          FROM models
         WHERE status='active'
           AND supports_tools=1
           AND accepts_substrate_system=1
           AND (context_window IS NULL OR context_window >= ?)
         ORDER BY provider, model_id
        """,
        (_SUBSTRATE_CONTEXT_MIN,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.post(
    "/models/{model_id}/route-to-agents",
    summary="Demote a model from the substrate picker to the agent surface",
)
def route_to_agents(model_id: int, con = Depends(get_db)):
    """Manual override for templates the static classifier doesn't catch —
    flips `accepts_substrate_system=0` so the row drops out of the picker
    immediately. The future agent UI pulls the complement set."""
    cur = con.execute(
        "UPDATE models SET accepts_substrate_system=0 WHERE model_id=?",
        (model_id,),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="model not found")
    con.commit()
    row = con.execute(
        "SELECT model_id, name, accepts_substrate_system FROM models WHERE model_id=?",
        (model_id,),
    ).fetchone()
    return dict(row)
