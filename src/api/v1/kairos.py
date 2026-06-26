"""Endpoints KAIROS — run, status, sequências, opt-out."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text as sql_text

from src.api.v1.admin import require_admin_key
from src.agents.kairos.graph import run_kairos
from src.agents.kairos.wa_escalation import process_wa_escalations
from src.database import AsyncSessionFactory

router = APIRouter(prefix="/api/v1/kairos", tags=["kairos"])


class KairosRunRequest(BaseModel):
    trigger_type: str = "manual"
    segment: str = "both"
    max_per_segment: int = 25
    brand_context: str = "VERTEX by Veltrus"


@router.post("/run")
async def kairos_run(
    payload: KairosRunRequest,
    _=Depends(require_admin_key),
):
    """Dispara um run do KAIROS em background."""
    asyncio.create_task(
        run_kairos(
            trigger_type=payload.trigger_type,
            segment=payload.segment,
            max_per_segment=payload.max_per_segment,
            brand_context=payload.brand_context,
        )
    )
    return {
        "status": "started",
        "trigger_type": payload.trigger_type,
        "segment": payload.segment,
    }


@router.get("/status")
async def kairos_status(_=Depends(require_admin_key)):
    """Estatísticas gerais das sequências KAIROS."""
    async with AsyncSessionFactory() as session:
        stats = await session.execute(
            sql_text("""
                SELECT status, COUNT(*) AS count, segment
                FROM kairos_sequences
                GROUP BY status, segment
                ORDER BY segment, status
            """)
        )
        rows = [dict(r._mapping) for r in stats.fetchall()]

        last_run = await session.execute(
            sql_text("""
                SELECT run_id, MAX(created_at) AS started_at, COUNT(*) AS sequences
                FROM kairos_sequences
                GROUP BY run_id
                ORDER BY started_at DESC
                LIMIT 5
            """)
        )
        runs = [dict(r._mapping) for r in last_run.fetchall()]

    return {"sequence_stats": rows, "recent_runs": runs}


@router.get("/sequences")
async def list_sequences(
    status: str | None = Query(None),
    segment: str | None = Query(None),
    limit: int = Query(50, le=200),
    _=Depends(require_admin_key),
):
    """Lista sequências com filtros opcionais."""
    where_clauses: list[str] = []
    params: dict = {"limit": limit}
    if status:
        where_clauses.append("status = :status")
        params["status"] = status
    if segment:
        where_clauses.append("segment = :segment")
        params["segment"] = segment
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            sql_text(f"""
                SELECT id, profile_id, segment, status, email,
                       email_sent_at, email_opened_at, wa_sent_at,
                       wa_replied_at, completed_at, outcome, created_at
                FROM kairos_sequences
                {where}
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            params,
        )
        rows = [dict(r._mapping) for r in result.fetchall()]

    return {"sequences": rows, "total": len(rows)}


@router.post("/escalate-wa")
async def trigger_wa_escalation(_=Depends(require_admin_key)):
    """Força escalação WhatsApp para emails não abertos > 48h."""
    return await process_wa_escalations()


@router.post("/opt-out/{profile_id}")
async def add_opt_out(profile_id: str, _=Depends(require_admin_key)):
    """Adiciona perfil à lista de opt-out."""
    import uuid as uuid_lib

    async with AsyncSessionFactory() as session:
        await session.execute(
            sql_text("""
                INSERT INTO kairos_opt_outs (id, profile_id)
                VALUES (:id, :pid)
                ON CONFLICT (profile_id) DO NOTHING
            """),
            {"id": str(uuid_lib.uuid4()), "pid": profile_id},
        )
        await session.execute(
            sql_text("""
                UPDATE kairos_sequences
                SET status = 'opted_out', completed_at = NOW()
                WHERE profile_id = :pid
                  AND status NOT IN ('completed', 'failed', 'opted_out')
            """),
            {"pid": profile_id},
        )
        await session.commit()
    return {"opted_out": True, "profile_id": profile_id}


@router.delete("/opt-out/{profile_id}")
async def remove_opt_out(profile_id: str, _=Depends(require_admin_key)):
    """Remove perfil da lista de opt-out."""
    async with AsyncSessionFactory() as session:
        await session.execute(
            sql_text("DELETE FROM kairos_opt_outs WHERE profile_id = :pid"),
            {"pid": profile_id},
        )
        await session.commit()
    return {"opted_in": True, "profile_id": profile_id}
