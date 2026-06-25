import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from src.main import app

SAMPLE_VTEX_WEBHOOK = {
    "Domain": "Fulfillment",
    "OrderId": "VLT-001",
    "State": "payment-approved",
    "Origin": {"Account": "veltrustest"},
}

SAMPLE_VTEX_ORDER_API = {
    "clientProfileData": {
        "email": "vtex@teste.com.br",
        "phone": "11988887777",
    },
    "marketingData": {
        "utmSource": "google",
        "utmMedium": "cpc",
        "utmCampaign": "vtex_test",
        "marketingTags": ["gclid:GCLID_VTEX_001"],
    },
    "totals": [
        {"id": "Items", "value": 19990},
        {"id": "Shipping", "value": 1000},
    ],
    "storePreferencesData": {"currencyCode": "BRL"},
}


def test_is_paid_state():
    from src.webhooks.vtex_parser import is_paid_state

    assert is_paid_state("payment-approved") is True
    assert is_paid_state("payment_approved") is True
    assert is_paid_state("waiting-for-authorization") is False


def test_extract_vtex_order_id():
    from src.webhooks.vtex_parser import extract_vtex_order_id

    assert extract_vtex_order_id(SAMPLE_VTEX_WEBHOOK) == "VLT-001"
    assert extract_vtex_order_id({"orderId": "ALT-99"}) == "ALT-99"


def test_extract_vtex_account():
    from src.webhooks.vtex_parser import extract_vtex_account

    assert extract_vtex_account(SAMPLE_VTEX_WEBHOOK) == "veltrustest"


def test_parse_vtex_order_details():
    from src.webhooks.vtex_parser import parse_vtex_order_details

    parsed = parse_vtex_order_details(SAMPLE_VTEX_ORDER_API)
    assert parsed["revenue"] == 209.9
    assert parsed["currency"] == "BRL"
    assert parsed["email"] == "vtex@teste.com.br"
    assert len(parsed["signals"]) == 2
    assert parsed["utms"]["gclid"] == "GCLID_VTEX_001"


def test_determine_vtex_channel_gclid():
    from src.webhooks.vtex_parser import determine_vtex_channel

    assert determine_vtex_channel({"gclid": "abc"}) == "google_ads"


@pytest.mark.asyncio
async def test_vtex_webhook_store_not_found():
    with patch(
        "src.api.v1.webhooks._get_vtex_store", AsyncMock(return_value=None)
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/vtex/orders",
                json=SAMPLE_VTEX_WEBHOOK,
                headers={
                    "X-VTEX-API-AppKey": "key",
                    "X-VTEX-API-AppToken": "token",
                },
            )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_vtex_webhook_not_paid():
    payload = {
        **SAMPLE_VTEX_WEBHOOK,
        "State": "waiting-for-authorization",
    }
    mock_store = {
        "account_name": "veltrustest",
        "app_key": "vtexappkey_test",
        "app_token": "vtexapptoken_test",
        "active": True,
        "meta_pixel_id": None,
        "meta_access_token": None,
        "meta_test_event_code": None,
    }
    with patch(
        "src.api.v1.webhooks._get_vtex_store", AsyncMock(return_value=mock_store)
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/vtex/orders",
                json=payload,
                headers={
                    "X-VTEX-API-AppKey": "vtexappkey_test",
                    "X-VTEX-API-AppToken": "vtexapptoken_test",
                },
            )
    assert response.status_code == 200
    assert response.json()["processed"] is False


@pytest.mark.asyncio
async def test_vtex_webhook_paid_accepted():
    mock_store = {
        "account_name": "veltrustest",
        "app_key": "vtexappkey_test",
        "app_token": "vtexapptoken_test",
        "active": True,
        "meta_pixel_id": None,
        "meta_access_token": None,
        "meta_test_event_code": None,
    }
    with (
        patch(
            "src.api.v1.webhooks._get_vtex_store", AsyncMock(return_value=mock_store)
        ),
        patch(
            "src.api.v1.webhooks.process_vtex_order", AsyncMock()
        ) as mock_process,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/vtex/orders",
                json=SAMPLE_VTEX_WEBHOOK,
                headers={
                    "X-VTEX-API-AppKey": "vtexappkey_test",
                    "X-VTEX-API-AppToken": "vtexapptoken_test",
                },
            )
    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["processed"] is True
    assert body["order_id"] == "VLT-001"
    mock_process.assert_called_once()
