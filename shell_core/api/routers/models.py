"""The model registry — read surface for the browser-chat model-switch dropdown,
plus the cloud activation/sync surface used by /ollamacloudconfig."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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


# ── Ollama Cloud config surface ───────────────────────────────────────────────
# Read + mutate cloud-model registry state from /ollamacloudconfig. The list
# endpoint includes inactive rows by design — the config page is where users
# see and flip them. The plain /models endpoint above stays activate-only so
# the picker dropdown remains short.


@router.get(
    "/models/cloud",
    summary="List every Ollama Cloud model row (active + inactive)",
)
def list_cloud_models(con = Depends(get_db)):
    rows = con.execute(
        """
        SELECT model_id, name, display_name, status, version,
               source_url, last_verified
          FROM models
         WHERE provider='ollama_cloud'
         ORDER BY (status='active') DESC, name
        """,
    ).fetchall()
    return [dict(r) for r in rows]


class _StatusBody(BaseModel):
    status: str = Field(pattern="^(active|inactive)$")


@router.patch(
    "/models/{model_id}/status",
    summary="Set a model's status (active|inactive)",
)
def set_model_status(model_id: int, body: _StatusBody, con = Depends(get_db)):
    cur = con.execute(
        "UPDATE models SET status=? WHERE model_id=?",
        (body.status, model_id),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="model not found")
    con.commit()
    row = con.execute(
        "SELECT model_id, name, status FROM models WHERE model_id=?",
        (model_id,),
    ).fetchone()
    return dict(row)


@router.post(
    "/models/cloud/sync",
    summary="Refresh the cloud-model catalog from Ollama Cloud's /api/tags",
)
def sync_cloud_models(con = Depends(get_db)):
    """Invoke the same sync the `make sync-cloud-models` CLI calls.
    Returns counts so the UI can surface what changed. Anonymous /api/tags
    read — no API key needed for catalog discovery."""
    # The sync logic lives in shell_core/scripts/cloud_model_sync.py;
    # load it via the same path trick the catalogue startup hook uses
    # (see main.py) so the script stays the canonical CLI tool.
    import sys as _sys
    from pathlib import Path
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    _sys.path.insert(0, str(scripts_dir))
    try:
        from cloud_model_sync import sync as _sync, _cloud_base, CatalogFetchError
    finally:
        if str(scripts_dir) in _sys.path:
            _sys.path.remove(str(scripts_dir))
    try:
        inserted, refreshed, deactivated = _sync(con, _cloud_base())
    except CatalogFetchError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"inserted": inserted, "refreshed": refreshed,
            "deactivated": deactivated}
