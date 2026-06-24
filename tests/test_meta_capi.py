import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_hash_is_sha256():
    from src.integrations.meta_capi import _hash

    expected = hashlib.sha256("test@example.com".encode()).hexdigest()
    assert _hash("test@example.com") == expected


def test_normalize_email():
    from src.integrations.meta_capi import _normalize_email

    assert _normalize_email("  TEST@Gmail.COM  ") == "test@gmail.com"


def test_normalize_phone_removes_non_digits():
    from src.integrations.meta_capi import _normalize_phone

    assert _normalize_phone("+55 (11) 99999-9999") == "5511999999999"


def test_build_purchase_event_structure():
    from src.integrations.meta_capi import build_purchase_event

    event = build_purchase_event(
        "12345", "test@example.com", "+5511999999999", 350.0, "BRL"
    )
    assert event["event_name"] == "Purchase"
    assert event["event_id"] == "shopify_12345"
    assert event["action_source"] == "website"
    assert "em" in event["user_data"]
    assert "ph" in event["user_data"]
    assert event["custom_data"]["value"] == 350.0
    assert event["custom_data"]["currency"] == "BRL"


def test_build_purchase_event_email_hashed():
    from src.integrations.meta_capi import _hash, _normalize_email, build_purchase_event

    event = build_purchase_event("1", "Test@Gmail.com", None, 100.0, "BRL")
    expected_hash = _hash(_normalize_email("Test@Gmail.com"))
    assert event["user_data"]["em"] == [expected_hash]


def test_build_purchase_event_no_pii_raises():
    from src.integrations.meta_capi import build_purchase_event

    with pytest.raises(ValueError, match="obrigatório"):
        build_purchase_event("1", None, None, 100.0, "BRL")


@pytest.mark.asyncio
async def test_send_purchase_skipped_when_not_configured():
    from src.integrations.meta_capi import send_purchase_event

    with patch("src.integrations.meta_capi.settings") as mock_settings:
        mock_settings.meta_pixel_id = ""
        mock_settings.meta_access_token = ""
        mock_settings.meta_test_event_code = ""
        result = await send_purchase_event("123", "a@b.com", None, 100.0, "BRL")
    assert result["status"] == "skipped"
    assert result["reason"] == "not_configured"


@pytest.mark.asyncio
async def test_send_purchase_ok():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"events_received": 1, "fbtrace_id": "abc123"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("src.integrations.meta_capi.settings") as mock_settings, patch(
        "src.integrations.meta_capi.httpx.AsyncClient", return_value=mock_ctx
    ):
        mock_settings.meta_pixel_id = "123456789"
        mock_settings.meta_access_token = "token_abc"
        mock_settings.meta_test_event_code = "TEST123"

        from src.integrations.meta_capi import send_purchase_event

        result = await send_purchase_event("999", "test@meta.com", None, 250.0, "BRL")

    assert result["status"] == "ok"
    assert result["events_received"] == 1
