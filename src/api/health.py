import asyncio

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.config import settings
from src.database import AsyncSessionFactory
from src.graphs.connection import execute_cypher
from src.nats_client import get_nats

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "veltrus-intelligence",
        "version": "0.8.0",
        "debug": settings.debug,
    }


@router.get("/health/detailed")
async def health_detailed():
    """
    Verifica conectividade com todos os serviços dependentes.
    Retorna 200 se tudo OK, 503 se qualquer serviço crítico falhou.
    """
    checks: dict = {}
    all_ok = True

    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = {"status": "ok"}
    except Exception as e:
        checks["postgres"] = {"status": "error", "error": str(e)[:100]}
        all_ok = False

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(
                f"http://{settings.qdrant_host}:{settings.qdrant_port}/healthz"
            )
            if response.status_code != 200:
                all_ok = False
            checks["qdrant"] = {
                "status": "ok" if response.status_code == 200 else "degraded",
            }
    except Exception as e:
        checks["qdrant"] = {"status": "error", "error": str(e)[:100]}
        all_ok = False

    try:
        nc = await get_nats()
        connected = nc.is_connected
        checks["nats"] = {"status": "ok" if connected else "disconnected"}
        if not connected:
            all_ok = False
    except Exception as e:
        checks["nats"] = {"status": "error", "error": str(e)[:100]}
        all_ok = False

    try:
        await asyncio.to_thread(execute_cypher, "SELECT 1 AS result")
        checks["graphdb"] = {"status": "ok"}
    except Exception as e:
        checks["graphdb"] = {"status": "error", "error": str(e)[:100]}
        all_ok = False

    try:
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema='public'"
                )
            )
            table_count = result.scalar()
        schema_status = "ok" if table_count >= 14 else "degraded"
        checks["schema"] = {
            "status": schema_status,
            "tables": table_count,
            "expected": 14,
        }
        if schema_status != "ok":
            all_ok = False
    except Exception as e:
        checks["schema"] = {"status": "error", "error": str(e)[:100]}
        all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse(
        content={
            "status": "ok" if all_ok else "degraded",
            "checks": checks,
        },
        status_code=status_code,
    )
