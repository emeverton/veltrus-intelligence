from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


def _mock_session_ctx(scalar_value=12):
    mock_result = MagicMock()
    mock_result.scalar.return_value = scalar_value
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    return mock_ctx


@pytest.mark.asyncio
async def test_health_simple():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.8.0"


@pytest.mark.asyncio
async def test_health_detailed_returns_checks_structure():
    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=mock_http_response)
    mock_http_ctx = AsyncMock()
    mock_http_ctx.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "src.api.health.AsyncSessionFactory",
        side_effect=[_mock_session_ctx(), _mock_session_ctx(12)],
    ), patch("src.api.health.httpx.AsyncClient", return_value=mock_http_ctx), patch(
        "src.api.health.get_nats", AsyncMock(return_value=MagicMock(is_connected=True))
    ), patch("src.api.health.execute_cypher", return_value=[{"result": 2}]), patch(
        "src.api.health.asyncio.to_thread",
        AsyncMock(return_value=[{"result": 2}]),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health/detailed")

    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "postgres" in data["checks"]
    assert "qdrant" in data["checks"]
    assert "nats" in data["checks"]
    assert "graphdb" in data["checks"]
    assert "schema" in data["checks"]
