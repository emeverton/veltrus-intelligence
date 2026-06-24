import asyncio
import logging
import uuid
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from src.config import settings

COLLECTION = "creative_embeddings"
VECTOR_SIZE = 384


def _get_client() -> QdrantClient:
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


def ensure_collection() -> None:
    """Cria a coleção se não existir."""
    client = _get_client()
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def upsert_creative(
    creative_id: str,
    vector: list[float],
    payload: dict,
) -> str:
    """Insere ou atualiza um criativo no Qdrant. Retorna o qdrant_id."""
    client = _get_client()
    qdrant_id = str(uuid.uuid5(uuid.NAMESPACE_URL, creative_id))
    client.upsert(
        collection_name=COLLECTION,
        points=[
            PointStruct(
                id=qdrant_id,
                vector=vector,
                payload={"creative_id": creative_id, **payload},
            )
        ],
    )
    return qdrant_id


def search_similar(
    query_vector: list[float],
    limit: int = 5,
    channel_filter: Optional[str] = None,
) -> list[dict]:
    """Busca criativos similares por vetor. Filtra por canal se informado."""
    client = _get_client()
    query_filter = None
    if channel_filter:
        query_filter = Filter(
            must=[FieldCondition(key="channel", match=MatchValue(value=channel_filter))]
        )
    results = client.search(
        collection_name=COLLECTION,
        query_vector=query_vector,
        limit=limit,
        query_filter=query_filter,
        with_payload=True,
    )
    return [
        {
            "creative_id": r.payload.get("creative_id"),
            "score": round(r.score, 4),
            "channel": r.payload.get("channel"),
            "description": r.payload.get("description"),
            "campaign_id": r.payload.get("campaign_id"),
        }
        for r in results
    ]


async def upsert_creative_async(creative_id: str, vector: list[float], payload: dict) -> str:
    return await asyncio.to_thread(upsert_creative, creative_id, vector, payload)


async def search_similar_async(
    query_vector: list[float],
    limit: int = 5,
    channel_filter: Optional[str] = None,
) -> list[dict]:
    return await asyncio.to_thread(search_similar, query_vector, limit, channel_filter)
