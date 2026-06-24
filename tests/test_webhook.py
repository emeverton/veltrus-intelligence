import base64
import hashlib
import hmac
import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


def make_shopify_signature(body: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), body, hashlib.sha256)
    return base64.b64encode(sig.digest()).decode()


SAMPLE_ORDER = {
    "id": 5001234567890,
    "order_number": 1042,
    "email": "cliente@exemplo.com.br",
    "phone": "+5511987654321",
    "total_price": "350.00",
    "currency": "BRL",
    "financial_status": "paid",
    "landing_site": (
        "https://loja.exemplo.com.br/produto"
        "?utm_source=google&utm_medium=cpc&utm_campaign=black_friday&gclid=Cj0KCQ"
    ),
    "referring_site": "https://www.google.com",
    "line_items": [
        {"product_id": 123, "title": "Produto Teste", "quantity": 1, "price": "350.00"}
    ],
}


@pytest.mark.asyncio
async def test_webhook_valid_hmac():
    secret = "test_secret_123"
    body = json.dumps(SAMPLE_ORDER).encode()
    sig = make_shopify_signature(body, secret)

    with patch("src.api.v1.webhooks.settings") as mock_settings, patch(
        "src.api.v1.webhooks.process_shopify_order", AsyncMock()
    ):
        mock_settings.shopify_webhook_secret = secret
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/webhooks/shopify/orders/paid",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Hmac-Sha256": sig,
                },
            )
    assert response.status_code == 200
    assert response.json()["received"] is True


@pytest.mark.asyncio
async def test_webhook_invalid_hmac_returns_401():
    body = json.dumps(SAMPLE_ORDER).encode()
    with patch("src.api.v1.webhooks.settings") as mock_settings:
        mock_settings.shopify_webhook_secret = "correct_secret"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/webhooks/shopify/orders/paid",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Hmac-Sha256": "invalid_signature",
                },
            )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_no_secret_accepts_with_warning():
    """Sem secret configurado: aceitar (desenvolvimento)."""
    body = json.dumps(SAMPLE_ORDER).encode()
    with patch("src.api.v1.webhooks.settings") as mock_settings, patch(
        "src.api.v1.webhooks.process_shopify_order", AsyncMock()
    ):
        mock_settings.shopify_webhook_secret = ""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/webhooks/shopify/orders/paid",
                content=body,
                headers={"Content-Type": "application/json"},
            )
    assert response.status_code == 200


def test_hmac_verifies_raw_bytes_not_reserialized_json():
    """HMAC deve ser calculado sobre bytes originais, não JSON re-serializado."""
    from src.webhooks.hmac_verify import verify_shopify_hmac

    secret = "test_secret"
    original = b'{"id":1,"email":"a@b.com","total_price":"100.00"}'
    reencoded = json.dumps(json.loads(original)).encode()

    sig = make_shopify_signature(original, secret)
    assert verify_shopify_hmac(original, secret, sig) is True
    assert verify_shopify_hmac(reencoded, secret, sig) is False


def test_extract_signals_email_and_phone():
    from src.webhooks.order_parser import extract_signals

    signals = extract_signals(SAMPLE_ORDER)
    types = [s["type"] for s in signals]
    assert "email" in types
    assert "phone" in types


def test_extract_signals_email_normalized():
    from src.webhooks.order_parser import extract_signals

    order = {"email": "  TESTE@Gmail.COM  "}
    signals = extract_signals(order)
    assert signals[0]["value"] == "teste@gmail.com"


def test_extract_utms_from_landing_site():
    from src.webhooks.order_parser import extract_utms

    utms = extract_utms(SAMPLE_ORDER)
    assert utms["utm_source"] == "google"
    assert utms["utm_medium"] == "cpc"
    assert utms["utm_campaign"] == "black_friday"
    assert utms["gclid"] == "Cj0KCQ"


def test_determine_channel_gclid():
    from src.webhooks.order_parser import determine_channel

    assert determine_channel({"gclid": "abc123"}) == "google_ads"


def test_determine_channel_fbclid():
    from src.webhooks.order_parser import determine_channel

    assert determine_channel({"fbclid": "abc123"}) == "meta_ads"


def test_determine_channel_utm_medium_cpc():
    from src.webhooks.order_parser import determine_channel

    assert determine_channel({"utm_medium": "cpc"}) == "google_ads"


def test_determine_channel_direct():
    from src.webhooks.order_parser import determine_channel

    assert determine_channel({}) == "direct"


def test_extract_revenue_string_price():
    from src.webhooks.order_parser import extract_revenue

    price, currency = extract_revenue({"total_price": "350.00", "currency": "BRL"})
    assert price == 350.0
    assert currency == "BRL"


def test_save_order_has_on_conflict_do_nothing():
    """Idempotência: INSERT deve usar ON CONFLICT DO NOTHING."""
    from src.webhooks import shopify_handler

    source = inspect.getsource(shopify_handler._save_order_record)
    assert "ON CONFLICT (shopify_order_id) DO NOTHING" in source


@pytest.mark.asyncio
async def test_process_shopify_order_idempotent_skips_duplicate():
    """Teste #7: ordem já processada não re-resolve identidade."""
    from src.webhooks.shopify_handler import process_shopify_order

    mock_existing = MagicMock()
    mock_existing.fetchone.return_value = ("existing-row-id",)

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_existing

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_session
    mock_ctx.__aexit__.return_value = None

    with patch("src.webhooks.shopify_handler.AsyncSessionFactory", return_value=mock_ctx), patch(
        "src.webhooks.shopify_handler.resolve_identity", AsyncMock()
    ) as mock_resolve:
        await process_shopify_order(SAMPLE_ORDER)
        mock_resolve.assert_not_called()
