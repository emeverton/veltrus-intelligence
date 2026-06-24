import asyncio
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.embeddings.model import encode_text_async
from src.embeddings.qdrant_ops import ensure_collection, search_similar_async, upsert_creative_async
from src.graphs.creative_graph import query_top_creatives_by_revenue, sync_creative_to_graph

router = APIRouter()


class CreativeIngestRequest(BaseModel):
    channel: str
    creative_type: str
    description: str
    name: Optional[str] = None
    campaign_id: Optional[str] = None
    external_id: Optional[str] = None
    metadata: Optional[dict] = None


@router.post("/ingest")
async def ingest_creative(
    payload: CreativeIngestRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Ingere um criativo:
    1. Gera embedding do campo description (fastembed, CPU)
    2. Upsert no Qdrant (creative_embeddings)
    3. Salva em creative_assets (Postgres)
    4. Sincroniza nó Creative no Revenue Graph (AGE) — fire-and-forget
    """
    creative_id = str(uuid.uuid4())

    vector = await encode_text_async(payload.description)

    ensure_collection()
    qdrant_id = await upsert_creative_async(
        creative_id,
        vector,
        {
            "channel": payload.channel,
            "creative_type": payload.creative_type,
            "description": payload.description,
            "campaign_id": payload.campaign_id,
        },
    )

    await session.execute(
        text("""
            INSERT INTO creative_assets
                (id, campaign_id, channel, creative_type, name, description,
                 external_id, qdrant_id, metadata)
            VALUES
                (:id, :campaign_id, :channel, :creative_type, :name, :description,
                 :external_id, :qdrant_id, :metadata)
        """),
        {
            "id": creative_id,
            "campaign_id": payload.campaign_id,
            "channel": payload.channel,
            "creative_type": payload.creative_type,
            "name": payload.name,
            "description": payload.description,
            "external_id": payload.external_id,
            "qdrant_id": qdrant_id,
            "metadata": json.dumps(payload.metadata or {}),
        },
    )
    await session.commit()

    asyncio.create_task(
        sync_creative_to_graph(
            creative_id, payload.channel, payload.creative_type, payload.campaign_id
        )
    )

    return {
        "creative_id": creative_id,
        "qdrant_id": qdrant_id,
        "vector_dims": len(vector),
    }


@router.get("/search")
async def search_similar_creatives(
    q: str = Query(description="Texto para busca por similaridade"),
    limit: int = Query(default=5, ge=1, le=20),
    channel: Optional[str] = Query(default=None),
):
    """Busca criativos similares por embedding do texto informado."""
    vector = await encode_text_async(q)
    results = await search_similar_async(vector, limit=limit, channel_filter=channel)
    return {"query": q, "results": results, "total": len(results)}


@router.get("/top-by-revenue")
async def top_creatives_by_revenue(
    limit: int = Query(default=10, ge=1, le=50),
):
    """Criativos com maior revenue atribuído via Revenue Graph."""
    results = await asyncio.to_thread(query_top_creatives_by_revenue, limit)
    return {"results": results, "total": len(results)}
