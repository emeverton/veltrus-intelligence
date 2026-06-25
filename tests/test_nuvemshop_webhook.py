import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from src.main import app

SAMPLE_NUVEMSHOP_PAYLOAD = {
    "store_id": 99999,
    "id": 55001,
    "payment_status": "paid",
    "total": "250.00",
    "currency": "BRL",
    "contact_email": "nuvem@teste.com.br",
    "contact_phone": "11977776666",
    "landing_url": "https://loja.com?utm_source=facebook&utm_medium=cpc&fbclid=FB_NUVEM_001",
}


def test_extract_nuvemshop_signals():
    from src.webhooks.nuvemshop_parser import extract_nuvemshop_signals

    signals = extract_nuvemshop_signals(SAMPLE_NUVEMSHOP_PAYLOAD)
    types = [s["type"] for s in signals]
    assert "email" in types
    assert "phone" in types


def test_extract_nuvemshop_utms():
    from src.webhooks.nuvemshop_parser import extract_nuvemshop_utms

    utms = extract_nuvemshop_utms(SAMPLE_NUVEMSHOP_PAYLOAD)
    assert utms["utm_source"] == "facebook"
    assert utms["fbclid"] == "FB_NUVEM_001"


def test_determine_nuvemshop_channel_fbclid():
    from src.webhooks.nuvemshop_parser import determine_nuvemshop_channel

    assert determine_nuvemshop_channel({"fbclid": "abc"}) == "meta_ads"


def test_is_nuvemshop_paid():
    from src.webhooks.nuvemshop_parser import is_paid_order

    assert is_paid_order(SAMPLE_NUVEMSHOP_PAYLOAD) is True


def test_is_nuvemshop_not_paid():
    from src.webhooks.nuvemshop_parser import is_paid_order

    assert is_paid_order({"payment_status": "pending"}) is False


def test_extract_nuvemshop_revenue():
    from src.webhooks.nuvemshop_parser import extract_nuvemshop_revenue

    price, currency = extract_nuvemshop_revenue(SAMPLE_NUVEMSHOP_PAYLOAD)
    assert price == 250.0
    assert currency == "BRL"


@pytest.mark.asyncio
async def test_nuvemshop_webhook_store_not_found():
    with patch(
        "src.api.v1.webhooks._get_nuvemshop_store", AsyncMock(return_value=None)
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/nuvemshop/orders",
                json=SAMPLE_NUVEMSHOP_PAYLOAD,
                headers={"Authorization": "Token token=valid_key"},
            )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_nuvemshop_webhook_not_paid():
    payload = {**SAMPLE_NUVEMSHOP_PAYLOAD, "payment_status": "pending"}
    mock_store = {
        "store_id": "99999",
        "api_key": "test_key",
        "active": True,
        "meta_pixel_id": None,
        "meta_access_token": None,
        "meta_test_event_code": None,
    }
    with patch(
        "src.api.v1.webhooks._get_nuvemshop_store", AsyncMock(return_value=mock_store)
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/nuvemshop/orders",
                json=payload,
                headers={"Authorization": "Token token=test_key"},
            )
    assert response.status_code == 200
    assert response.json()["processed"] is False
