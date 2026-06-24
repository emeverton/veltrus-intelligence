import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import get_session
from src.main import app


async def _mock_get_session():
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    yield mock_db


@pytest.mark.asyncio
async def test_ingest_creative_returns_ids():
    mock_vector = [0.1] * 384
    with patch("src.api.v1.creatives.encode_text_async", AsyncMock(return_value=mock_vector)), \
         patch("src.api.v1.creatives.ensure_collection"), \
         patch("src.api.v1.creatives.upsert_creative_async", AsyncMock(return_value="qdrant-id-123")), \
         patch("src.api.v1.creatives.sync_creative_to_graph", new_callable=AsyncMock):

        app.dependency_overrides[get_session] = _mock_get_session
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/creatives/ingest",
                    json={
                        "channel": "google_ads",
                        "creative_type": "text",
                        "description": "Máquinas CNC de alta precisão para metalurgia",
                        "campaign_id": "camp_001",
                    },
                )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "creative_id" in data
    assert data["vector_dims"] == 384


@pytest.mark.asyncio
async def test_search_creatives():
    mock_vector = [0.1] * 384
    mock_results = [
        {
            "creative_id": "abc",
            "score": 0.92,
            "channel": "google_ads",
            "description": "...",
            "campaign_id": "c1",
        }
    ]
    with patch("src.api.v1.creatives.encode_text_async", AsyncMock(return_value=mock_vector)), \
         patch("src.api.v1.creatives.search_similar_async", AsyncMock(return_value=mock_results)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/creatives/search?q=cortador+cnc")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["results"][0]["score"] == 0.92


def test_embed_produces_384_dims():
    """Teste de integração leve — roda fastembed real sem mock."""
    from src.embeddings.model import encode_text

    vector = encode_text("teste de embedding em português")
    assert len(vector) == 384
    assert all(isinstance(v, float) for v in vector)


def test_creative_graph_upsert_uses_correct_age_pattern():
    """Verifica que o código não usa ON CREATE SET (padrão inválido no AGE)."""
    from src.graphs import creative_graph

    source = inspect.getsource(creative_graph)
    assert "ON CREATE SET" not in source, "ON CREATE SET não é suportado nesta versão do AGE"


def test_ensure_collection_idempotent():
    """ensure_collection() não deve lançar se collection já existe."""
    mock_client = MagicMock()
    existing_col = MagicMock()
    existing_col.name = "creative_embeddings"
    mock_client.get_collections.return_value.collections = [existing_col]
    with patch("src.embeddings.qdrant_ops._get_client", return_value=mock_client):
        from src.embeddings.qdrant_ops import ensure_collection

        ensure_collection()
        mock_client.create_collection.assert_not_called()
