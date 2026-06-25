import base64
import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from src.main import app

SECRET = "test_wc_secret"

WC_ORDER_PAID = (
    b'{"id":5001,"status":"processing","total":"199.90","currency":"BRL",'
    b'"billing":{"email":"wc@test.com.br","phone":"11988887777"},'
    b'"meta_data":[{"key":"utm_source","value":"google"},'
    b'{"key":"utm_medium","value":"cpc"},{"key":"gclid","value":"GCLID_WC_001"}]}'
)


def make_wc_signature(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


def test_verify_woocommerce_hmac():
    from src.webhooks.woocommerce_parser import verify_woocommerce_hmac

    sig = make_wc_signature(WC_ORDER_PAID, SECRET)
    assert verify_woocommerce_hmac(WC_ORDER_PAID, SECRET, sig) is True
    assert verify_woocommerce_hmac(WC_ORDER_PAID, SECRET, "invalido") is False


def test_verify_woocommerce_not_shopify_hex():
    """WooCommerce usa base64 — assinatura hex (Shopify) deve falhar."""
    from src.webhooks.woocommerce_parser import verify_woocommerce_hmac

    hex_sig = hmac.new(SECRET.encode(), WC_ORDER_PAID, hashlib.sha256).hexdigest()
    assert verify_woocommerce_hmac(WC_ORDER_PAID, SECRET, hex_sig) is False


def test_wc_is_paid():
    from src.webhooks.woocommerce_parser import is_paid_order

    assert is_paid_order({"status": "processing"}) is True
    assert is_paid_order({"status": "completed"}) is True
    assert is_paid_order({"status": "pending"}) is False
    assert is_paid_order({"status": "on-hold"}) is False


def test_extract_wc_utms():
    from src.webhooks.woocommerce_parser import extract_woocommerce_utms

    order = json.loads(WC_ORDER_PAID)
    utms = extract_woocommerce_utms(order)
    assert utms["utm_source"] == "google"
    assert utms["gclid"] == "GCLID_WC_001"


def test_extract_wc_signals():
    from src.webhooks.woocommerce_parser import extract_woocommerce_signals

    order = json.loads(WC_ORDER_PAID)
    signals = extract_woocommerce_signals(order)
    assert any(s["type"] == "email" for s in signals)
    assert any(s["type"] == "phone" for s in signals)


@pytest.mark.asyncio
async def test_wc_webhook_store_not_found():
    sig = make_wc_signature(WC_ORDER_PAID, SECRET)
    with patch(
        "src.api.v1.webhooks._resolve_woocommerce_store", AsyncMock(return_value=None)
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/woocommerce/orders",
                content=WC_ORDER_PAID,
                headers={
                    "Content-Type": "application/json",
                    "X-WC-Webhook-Signature": sig,
                    "X-WC-Webhook-Source": "https://minhaloja.com.br",
                },
            )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_wc_webhook_invalid_hmac():
    mock_store = {
        "store_url": "https://minhaloja.com.br",
        "webhook_secret": SECRET,
        "active": True,
    }
    with patch(
        "src.api.v1.webhooks._resolve_woocommerce_store",
        AsyncMock(return_value=mock_store),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/woocommerce/orders",
                content=WC_ORDER_PAID,
                headers={
                    "Content-Type": "application/json",
                    "X-WC-Webhook-Signature": "bad-signature",
                    "X-WC-Webhook-Source": "https://minhaloja.com.br",
                },
            )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generic_order_missing_store_id():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/webhooks/generic/order",
            json={"order_id": "1", "revenue": 100},
            headers={"X-Store-Key": "key"},
        )
    assert response.status_code == 400
