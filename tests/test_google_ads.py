from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_upload_skipped_when_not_configured():
    from src.integrations.google_ads import upload_conversion

    with patch("src.integrations.google_ads.settings") as mock_cfg:
        mock_cfg.google_ads_developer_token = ""
        result = await upload_conversion(
            "gclid123", "1234567890", "customers/123/conversionActions/456", 100.0, "BRL"
        )
    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_upload_skipped_without_conversion_action():
    from src.integrations.google_ads import upload_conversion

    with patch("src.integrations.google_ads.settings") as mock_cfg:
        mock_cfg.google_ads_developer_token = "dev_token"
        mock_cfg.google_ads_client_id = "client"
        mock_cfg.google_ads_client_secret = "secret"
        mock_cfg.google_ads_refresh_token = "refresh"
        result = await upload_conversion("gclid123", "1234567890", "", 100.0, "BRL")
    assert result["status"] == "skipped"
    assert result["reason"] == "no_conversion_action"


def test_conversion_datetime_format():
    """Formato de data deve ser aceito pelo Google Ads API."""
    dt = datetime.now(timezone.utc)
    formatted = dt.strftime("%Y-%m-%d %H:%M:%S+00:00")
    assert len(formatted) == 25
    assert "+" in formatted


@pytest.mark.asyncio
async def test_upload_ok_mocked():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": [{"gclid": "test"}]}

    async def mock_get_token():
        return "access_token_abc"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("src.integrations.google_ads._get_access_token", mock_get_token), patch(
        "src.integrations.google_ads.settings"
    ) as mock_cfg, patch(
        "src.integrations.google_ads.httpx.AsyncClient", return_value=mock_ctx
    ):
        mock_cfg.google_ads_developer_token = "dev_token"
        from src.integrations.google_ads import upload_conversion

        result = await upload_conversion(
            "gclid_test",
            "1234567890",
            "customers/1234567890/conversionActions/987654321",
            350.0,
            "BRL",
        )
    assert result["status"] == "ok"
