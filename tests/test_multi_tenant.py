from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_webhook_routes_by_shop_domain():
    """Webhook usa secret da store no banco quando domain está presente."""
    mock_store = MagicMock()
    mock_store.webhook_secret = "store_secret_abc"

    with patch(
        "src.api.v1.webhooks.store_repo.get_by_domain",
        AsyncMock(return_value=mock_store),
    ), patch("src.api.v1.webhooks.verify_shopify_hmac", return_value=True), patch(
        "src.api.v1.webhooks.process_shopify_order", AsyncMock()
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/webhooks/shopify/orders/paid",
                content=b'{"id":1234,"total_price":"100.00","financial_status":"paid"}',
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Shop-Domain": "test-store.myshopify.com",
                    "X-Shopify-Hmac-Sha256": "valid",
                },
            )
    assert response.status_code == 200
    assert response.json()["shop_domain"] == "test-store.myshopify.com"


@pytest.mark.asyncio
async def test_webhook_falls_back_to_env_secret():
    """Sem store no banco: usar SHOPIFY_WEBHOOK_SECRET do .env."""
    with patch(
        "src.api.v1.webhooks.store_repo.get_by_domain", AsyncMock(return_value=None)
    ), patch("src.api.v1.webhooks.verify_shopify_hmac", return_value=True), patch(
        "src.api.v1.webhooks.process_shopify_order", AsyncMock()
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/webhooks/shopify/orders/paid",
                content=b'{"id":5678,"total_price":"50.00","financial_status":"paid"}',
                headers={"Content-Type": "application/json"},
            )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_requires_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/stores", headers={"X-Admin-Key": "wrong"}
        )
    assert response.status_code in (403, 503)


def test_store_schema_validation():
    from src.stores.schemas import StoreCreate

    store = StoreCreate(
        shop_domain="loja.myshopify.com",
        webhook_secret="shpss_abc123",
    )
    assert store.shop_domain == "loja.myshopify.com"
    assert store.meta_pixel_id is None
