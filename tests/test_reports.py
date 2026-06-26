"""Testes dos endpoints de relatório."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app

ADMIN_HEADERS = {"X-Admin-Key": "test_admin_key"}

MOCK_METRICS = {
    "period": {"start": "01/01/2025", "end": "07/01/2025"},
    "current_week": {
        "order_count": 5,
        "total_revenue": 1250.0,
        "avg_order_value": 250.0,
        "unique_customers": 4,
    },
    "previous_week": {"total_revenue": 1000.0},
    "revenue_change_pct": 25.0,
    "top_channels": [{"channel": "google_ads", "order_count": 3, "revenue": 750.0}],
    "top_campaign": "campanha_teste",
    "platform": "shopify",
    "store_identifier": "test.myshopify.com",
}


@pytest.fixture(autouse=True)
def _admin_key():
    with patch("src.api.v1.admin.settings.admin_api_key", "test_admin_key"):
        yield


@pytest.mark.asyncio
async def test_weekly_report_invalid_platform():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/reports/weekly",
            params={"platform": "invalid", "store_identifier": "x"},
            headers=ADMIN_HEADERS,
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_weekly_report_valid():
    with patch(
        "src.api.v1.reports.get_weekly_metrics",
        AsyncMock(return_value=MOCK_METRICS),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/reports/weekly",
                params={
                    "platform": "shopify",
                    "store_identifier": "test.myshopify.com",
                },
                headers=ADMIN_HEADERS,
            )
    assert response.status_code == 200
    data = response.json()
    assert data["current_week"]["total_revenue"] == 1250.0
    assert data["revenue_change_pct"] == 25.0


@pytest.mark.asyncio
async def test_weekly_all_stores():
    with patch(
        "src.api.v1.reports.get_all_active_stores_metrics",
        AsyncMock(return_value=[MOCK_METRICS]),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/reports/weekly/all-stores",
                headers=ADMIN_HEADERS,
            )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["stores"][0]["platform"] == "shopify"


def test_week_range():
    from src.reports.aggregator import get_week_range

    start, end = get_week_range(1)
    assert start < end
    assert (end - start).days >= 6
