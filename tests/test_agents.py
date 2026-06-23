import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from src.database import get_session
from src.main import app


async def _mock_get_session():
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    yield mock_db


@pytest.mark.asyncio
async def test_run_agent_returns_job_id():
    with patch("src.api.v1.agents.publish", AsyncMock()):
        app.dependency_overrides[get_session] = _mock_get_session
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/agents/run",
                    json={"task": "Qual canal gerou mais receita?"},
                )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_get_agent_status_not_found():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    async def _mock_session():
        yield mock_db

    app.dependency_overrides[get_session] = _mock_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/agents/status/00000000-0000-0000-0000-000000000000"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_tools_definition_structure():
    """Valida que todos os tools têm name, description e input_schema."""
    from src.agents.tools import TOOLS

    for tool in TOOLS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_forecast_returns_dict_on_empty_data():
    """forecast_revenue_async com dados vazios deve retornar status insufficient_data."""
    empty_df = MagicMock()
    empty_df.empty = True
    empty_df.__len__ = MagicMock(return_value=0)

    with patch(
        "src.agents.forecast._load_revenue_data",
        AsyncMock(return_value=empty_df),
    ):
        from src.agents.forecast import forecast_revenue_async

        result = await forecast_revenue_async(30)

    assert result["status"] == "insufficient_data"


def test_max_iterations_guard():
    """Verificar que MAX_ITERATIONS está definido e é razoável."""
    from src.agents.graph import MAX_ITERATIONS

    assert 3 <= MAX_ITERATIONS <= 10, "MAX_ITERATIONS deve estar entre 3 e 10"
