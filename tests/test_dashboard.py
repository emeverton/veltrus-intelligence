import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_dashboard_returns_html():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "VELTRUS" in response.text
    assert "Chart.js" in response.text


@pytest.mark.asyncio
async def test_dashboard_contains_api_calls():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/dashboard")
    html = response.text
    assert "/api/v1/analytics/summary" in html
    assert "/api/v1/agents/run" in html
    assert "Chakra Petch" in html
    assert "localStorage" in html
