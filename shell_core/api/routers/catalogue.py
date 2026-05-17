"""Catalogue read — the dr_* substrate index, surfaced over the API."""
from fastapi import APIRouter, Depends

from api.common.db import get_db

router = APIRouter(tags=["catalogue"])


@router.get("/catalogue", summary="List the substrate catalogue (dr_* components); optional table + q filters")
def get_catalogue(table: str = "", q: str = "", con = Depends(get_db)):
    """The dr_* index — routes, routers, deps, libs, services, repos, files,
    automations, env. Open to any caller; not an admin surface."""
    sql = "SELECT ref_table, ref_id, name, description_short FROM v_dr_catalogue"
    where, args = [], []
    if table:
        where.append("ref_table = ?"); args.append(table)
    if q:
        where.append("(name LIKE ? OR description_short LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ref_table, name"
    return [dict(r) for r in con.execute(sql, args).fetchall()]
