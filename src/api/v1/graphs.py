import asyncio

from fastapi import APIRouter, Query

from src.graphs.revenue_graph import query_identity_ltv, query_revenue_by_channel

router = APIRouter()


@router.get("/revenue-by-channel")
async def revenue_by_channel(
    model: str = Query(default="linear", description="Modelo de atribuição"),
    limit: int = Query(default=10, ge=1, le=100),
):
    """Revenue total por canal para o modelo de atribuição informado."""
    results = await asyncio.to_thread(query_revenue_by_channel, model, limit)
    return {"model": model, "results": results, "total": len(results)}


@router.get("/identity-ltv")
async def identity_ltv(
    min_revenue: float = Query(default=0.0, description="Filtro mínimo de revenue por conversão"),
    limit: int = Query(default=10, ge=1, le=100),
):
    """Top identidades por LTV (soma de conversões no grafo)."""
    results = await asyncio.to_thread(query_identity_ltv, min_revenue, limit)
    return {"results": results, "total": len(results)}
