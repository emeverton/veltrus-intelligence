import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from src.main import app

LI_STORE_KEY = "li-test-store"
LI_API_KEY = "li_test_key_001"
MOOVIN_STORE_ID = "a24f51bc-5c08-4b7e-ba3c-51fdd4d5d24b"
MOOVIN_API_KEY = "moovin_test_key_001"

LI_ORDER_PAID = {
    "id": 8001,
    "situacao": {"id": 2, "nome": "Aprovado"},
    "total": "280.00",
    "moeda": "BRL",
    "cliente": {"email": "li@test.com.br", "fone": "11966665555"},
    "utm": {"utm_source": "google", "utm_medium": "cpc", "gclid": "GCLID_LI_001"},
    "loja": LI_STORE_KEY,
}

MOOVIN_ORDER_PAID = {
    "id": "MOOVIN-TEST-001",
    "status": "aprovado",
    "total": 350.00,
    "currency": "BRL",
    "customer": {"email": "malhas@test.com.br", "phone": "51988887777"},
    "utm": {"utm_source": "facebook", "fbclid": "FB_MOOVIN_001"},
}


def test_li_is_paid():
    from src.webhooks.loja_integrada_parser import is_paid_order

    assert is_paid_order({"situacao": {"id": 2}}) is True
    assert is_paid_order({"situacao": {"id": 5}}) is True
    assert is_paid_order({"situacao": {"id": 7}}) is False
    assert is_paid_order({"situacao": {"id": 6}}) is False


def test_li_extract_order_id():
    from src.webhooks.loja_integrada_parser import extract_li_order_id

    assert extract_li_order_id({"id": 8001}) == "8001"
    assert extract_li_order_id({"numero": 42}) == "42"


def test_li_extract_signals():
    from src.webhooks.loja_integrada_parser import extract_li_signals

    signals = extract_li_signals(LI_ORDER_PAID)
    assert any(s["type"] == "email" for s in signals)
    assert any(s["type"] == "phone" for s in signals)


def test_moovin_is_paid():
    from src.webhooks.moovin_parser import is_paid_order

    assert is_paid_order({"status": "aprovado"}) is True
    assert is_paid_order({"status_id": 2}) is True
    assert is_paid_order({"payment_status": "paid"}) is True
    assert is_paid_order({"status": "pendente"}) is False


def test_moovin_extract_signals():
    from src.webhooks.moovin_parser import extract_moovin_signals

    signals = extract_moovin_signals(MOOVIN_ORDER_PAID)
    assert any(s["type"] == "email" for s in signals)
    assert any(s["type"] == "phone" for s in signals)


@pytest.mark.asyncio
async def test_li_webhook_not_paid():
    mock_store = {
        "store_key": LI_STORE_KEY,
        "api_key": LI_API_KEY,
        "active": True,
    }
    with patch("src.api.v1.webhooks._get_li_store", AsyncMock(return_value=mock_store)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/loja-integrada/orders",
                json={
                    "id": 8002,
                    "situacao": {"id": 7, "nome": "Não Aprovado"},
                    "total": "100.00",
                    "loja": LI_STORE_KEY,
                },
                headers={"Authorization": f"chave {LI_API_KEY}"},
            )
    assert response.status_code == 200
    assert response.json()["processed"] is False


@pytest.mark.asyncio
async def test_li_webhook_store_not_found():
    with patch("src.api.v1.webhooks._get_li_store", AsyncMock(return_value=None)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/loja-integrada/orders",
                json=LI_ORDER_PAID,
                headers={"Authorization": f"chave {LI_API_KEY}"},
            )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_moovin_webhook_store_not_found():
    with patch("src.api.v1.webhooks._get_moovin_store", AsyncMock(return_value=None)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/moovin/orders",
                json=MOOVIN_ORDER_PAID,
                headers={
                    "X-Store-Key": MOOVIN_API_KEY,
                    "X-Store-Id": MOOVIN_STORE_ID,
                },
            )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_moovin_webhook_missing_store_id():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/webhooks/moovin/orders",
            json={"id": "1", "status": "aprovado"},
            headers={"X-Store-Key": MOOVIN_API_KEY},
        )
    assert response.status_code == 400
