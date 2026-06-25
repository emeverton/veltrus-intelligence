from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


def _mock_scalar(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _mock_fetchone(row):
    result = MagicMock()
    result.fetchone.return_value = row
    return result


def _mock_fetchall(rows):
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


@pytest.mark.asyncio
async def test_analytics_summary_structure():
    """Verifica estrutura do response mesmo sem dados reais."""
    conv_row = MagicMock()
    conv_row.total = 5
    conv_row.total_revenue = 1500.0
    conv_row.currency = "BRL"

    channel_row = MagicMock()
    channel_row.channel = "google_ads"
    channel_row.conversions = 3
    channel_row.revenue_credit = 900.0

    ltv_row = MagicMock()
    ltv_row.profile_id = "00000000-0000-0000-0000-000000000001"
    ltv_row.conversions = 2
    ltv_row.ltv = 800.0

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=[
            _mock_scalar(10),
            _mock_fetchone(conv_row),
            _mock_fetchall([channel_row]),
            _mock_fetchall([ltv_row]),
            _mock_scalar(4),
        ]
    )

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_session
    mock_ctx.__aexit__.return_value = None

    with patch("src.api.v1.analytics.AsyncSessionFactory", return_value=mock_ctx):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/analytics/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["period"] == "last_30_days"
    assert "profiles" in data
    assert "conversions" in data
    assert "revenue_by_channel" in data
    assert "top_profiles_by_ltv" in data
    assert "shopify_orders" in data
    assert data["profiles"]["total"] == 10
    assert data["shopify_orders"] == 4
    assert data["shop_domain"] is None


@pytest.mark.asyncio
async def test_analytics_summary_shop_domain_filter():
    conv_row = MagicMock()
    conv_row.total = 2
    conv_row.total_revenue = 500.0
    conv_row.currency = "BRL"

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=[
            _mock_scalar(10),
            _mock_scalar(1),
            _mock_fetchone(conv_row),
            _mock_fetchall([]),
            _mock_fetchall([]),
        ]
    )

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_session
    mock_ctx.__aexit__.return_value = None

    with patch("src.api.v1.analytics.AsyncSessionFactory", return_value=mock_ctx):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/analytics/summary?shop_domain=mdadqp-ar.myshopify.com"
            )

    assert response.status_code == 200
    data = response.json()
    assert data["shop_domain"] == "mdadqp-ar.myshopify.com"
