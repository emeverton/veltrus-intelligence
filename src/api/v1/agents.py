import asyncio
import json
import uuid
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.nats_client import publish

router = APIRouter()
AGENT_SUBJECT = "agents.jobs.run"


class AgentRunRequest(BaseModel):
    task: str
    context: Optional[dict] = None


@router.post("/run")
async def run_agent_job(
    payload: AgentRunRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Dispara um job de agente assíncrono.
    Retorna job_id para consultar status via /status/{job_id}.
    """
    job_id = str(uuid.uuid4())

    await session.execute(
        sql_text("""
            INSERT INTO agent_jobs (id, task, context, status)
            VALUES (:id, :task, CAST(:context AS jsonb), 'pending')
        """),
        {
            "id": job_id,
            "task": payload.task,
            "context": json.dumps(payload.context or {}),
        },
    )
    await session.commit()

    await publish(
        AGENT_SUBJECT,
        {
            "job_id": job_id,
            "task": payload.task,
            "context": payload.context or {},
        },
    )

    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Agente em processamento. Consulte /status/{job_id} para acompanhar.",
    }


@router.get("/status/{job_id}")
async def get_agent_status(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Retorna status e resultado de um job de agente."""
    result = await session.execute(
        sql_text(
            "SELECT id, task, status, result, error, created_at, updated_at "
            "FROM agent_jobs WHERE id=:id"
        ),
        {"id": str(job_id)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": str(row.id),
        "task": row.task,
        "status": row.status,
        "result": row.result,
        "error": row.error,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/jobs")
async def list_recent_jobs(
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """Lista os últimos jobs de agente."""
    result = await session.execute(
        sql_text("""
            SELECT id, task, status, created_at
            FROM agent_jobs
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    )
    rows = result.fetchall()
    return {
        "jobs": [
            {
                "job_id": str(r.id),
                "task": r.task[:80],
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }
