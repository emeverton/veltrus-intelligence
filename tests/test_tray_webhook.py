import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from src.main import app

SAMPLE_TRAY_PAYLOAD = {
    "seller_id": 12345,
    "order": {
        "id": 99001,
        "status_id": "7",
        "value": "450.00",
        "customer": {
            "email": "tray@teste.com.br",
            "phone": "(11) 99888-7777",
        },
        "utm": {
            "utm_source": "google",
            "utm_medium": "cpc",
            "utm_campaign": "tray_test",
            "gclid": "GCLID_TRAY_001",
        },
    },
}


def test_extract_tray_signals():
    from src.webhooks.tray_parser import extract_tray_signals

    signals = extract_tray_signals(SAMPLE_TRAY_PAYLOAD)
    types = [s["type"] for s in signals]
    assert "email" in types
    assert "phone" in types


def test_extract_tray_utms():
    from src.webhooks.tray_parser import extract_tray_utms

    utms = extract_tray_utms(SAMPLE_TRAY_PAYLOAD)
    assert utms["utm_source"] == "google"
    assert utms["gclid"] == "GCLID_TRAY_001"


def test_determine_tray_channel_gclid():
    from src.webhooks.tray_parser import determine_tray_channel

    assert determine_tray_channel({"gclid": "abc"}) == "google_ads"


def test_is_paid_order_status_7():
    from src.webhooks.tray_parser import is_paid_order

    assert is_paid_order(SAMPLE_TRAY_PAYLOAD) is True


def test_is_not_paid_order():
    from src.webhooks.tray_parser import is_paid_order

    payload = {"order": {"status_id": "2"}}
    assert is_paid_order(payload) is False


def test_extract_tray_revenue():
    from src.webhooks.tray_parser import extract_tray_revenue

    price, currency = extract_tray_revenue(SAMPLE_TRAY_PAYLOAD)
    assert price == 450.0
    assert currency == "BRL"


@pytest.mark.asyncio
async def test_tray_webhook_store_not_found():
    with patch(
        "src.api.v1.webhooks._get_tray_store", AsyncMock(return_value=None)
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/tray/orders",
                json=SAMPLE_TRAY_PAYLOAD,
                headers={"Authorization": "Token token=valid_key"},
            )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tray_webhook_not_paid_order():
    """Ordens não pagas devem retornar 200 mas processed=False."""
    payload = {
        **SAMPLE_TRAY_PAYLOAD,
        "order": {**SAMPLE_TRAY_PAYLOAD["order"], "status_id": "2"},
    }
    mock_store = {
        "seller_id": "12345",
        "api_key": "test_key",
        "active": True,
        "meta_pixel_id": None,
        "meta_access_token": None,
        "meta_test_event_code": None,
    }
    with patch(
        "src.api.v1.webhooks._get_tray_store", AsyncMock(return_value=mock_store)
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/tray/orders",
                json=payload,
                headers={"Authorization": "Token token=test_key"},
            )
    assert response.status_code == 200
    assert response.json()["processed"] is False
