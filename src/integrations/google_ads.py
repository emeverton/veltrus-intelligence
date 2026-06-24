"""
Google Ads Offline Conversion Upload.
Usa REST API diretamente (sem google-ads SDK pesado).
Requer: google-auth para refresh do token OAuth2.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from src.config import settings

logger = logging.getLogger(__name__)
GADS_API_VERSION = "v17"
UPLOAD_URL = (
    "https://googleads.googleapis.com/{version}/customers/{customer_id}"
    ":uploadClickConversions"
)


async def _get_access_token() -> str | None:
    """Obtém access token via refresh token OAuth2."""
    if not all([
        settings.google_ads_client_id,
        settings.google_ads_client_secret,
        settings.google_ads_refresh_token,
    ]):
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_ads_client_id,
                    "client_secret": settings.google_ads_client_secret,
                    "refresh_token": settings.google_ads_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            return response.json().get("access_token")
    except Exception as e:
        logger.error("Google OAuth token refresh failed: %s", e)
        return None


async def upload_conversion(
    gclid: str,
    customer_id: str,
    conversion_action: str,
    conversion_value: float,
    currency: str = "BRL",
) -> dict:
    """
    Faz upload de uma conversão offline para o Google Ads.
    Requer: GCLID da ordem + conversion_action resource name da loja.
    """
    if not settings.google_ads_developer_token:
        logger.info(
            "Google Ads não configurado (GOOGLE_ADS_DEVELOPER_TOKEN vazio) — skip"
        )
        return {"status": "skipped", "reason": "not_configured"}

    if not conversion_action:
        logger.warning(
            "google_ads_conversion_action não configurado para customer %s",
            customer_id,
        )
        return {"status": "skipped", "reason": "no_conversion_action"}

    access_token = await _get_access_token()
    if not access_token:
        return {"status": "error", "reason": "token_refresh_failed"}

    conversion_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")

    payload = {
        "conversions": [
            {
                "gclid": gclid,
                "conversionAction": conversion_action,
                "conversionDateTime": conversion_time,
                "conversionValue": round(conversion_value, 2),
                "currencyCode": currency.upper(),
            }
        ],
        "partialFailure": True,
    }

    customer_id_clean = customer_id.replace("-", "")
    url = UPLOAD_URL.format(version=GADS_API_VERSION, customer_id=customer_id_clean)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "developer-token": settings.google_ads_developer_token,
                    "Content-Type": "application/json",
                },
            )
            data = response.json()

        if response.status_code == 200:
            results = data.get("results", [])
            partial_errors = data.get("partialFailureError")
            if partial_errors:
                logger.error("Google Ads partial failure: %s", partial_errors)
                return {"status": "partial_error", "details": partial_errors}
            logger.info(
                "Google Ads conversion uploaded: gclid=%s..., value=%s",
                gclid[:10],
                conversion_value,
            )
            return {"status": "ok", "results": results}

        logger.error("Google Ads API error %s: %s", response.status_code, data)
        return {"status": "error", "http_status": response.status_code, "details": data}

    except Exception as e:
        logger.error("Google Ads upload failed: %s", e)
        return {"status": "error", "error": str(e)}
