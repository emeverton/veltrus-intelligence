"""
Meta Conversions API (CAPI) — server-side event sending.
Documentação: https://developers.facebook.com/docs/marketing-api/conversions-api
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)
META_CAPI_URL = "https://graph.facebook.com/v21.0/{pixel_id}/events"


def _hash(value: str) -> str:
    """SHA256 de um valor normalizado. Exigido pela Meta para PII."""
    return hashlib.sha256(value.strip().encode()).hexdigest()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_phone(phone: str) -> str:
    """Remove todos os caracteres não numéricos. Meta exige apenas dígitos."""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("55") and len(digits) == 13:
        return digits
    if len(digits) == 11 and digits.startswith("0"):
        return "55" + digits[1:]
    return digits


def build_purchase_event(
    shopify_order_id: str,
    email: Optional[str],
    phone: Optional[str],
    revenue: float,
    currency: str,
    event_source_url: Optional[str] = None,
) -> dict:
    """
    Constrói um evento Purchase para o Meta CAPI.
    Pelo menos um campo de user_data é obrigatório (email ou phone).
    """
    user_data: dict[str, list[str]] = {}
    if email:
        user_data["em"] = [_hash(_normalize_email(email))]
    if phone:
        user_data["ph"] = [_hash(_normalize_phone(phone))]

    if not user_data:
        raise ValueError("Ao menos email ou phone é obrigatório para o Meta CAPI")

    event: dict = {
        "event_name": "Purchase",
        "event_time": int(time.time()),
        "event_id": f"shopify_{shopify_order_id}",
        "action_source": "website",
        "user_data": user_data,
        "custom_data": {
            "value": round(revenue, 2),
            "currency": currency.upper(),
        },
    }
    if event_source_url:
        event["event_source_url"] = event_source_url

    return event


async def send_purchase_event(
    shopify_order_id: str,
    email: Optional[str],
    phone: Optional[str],
    revenue: float,
    currency: str,
    event_source_url: Optional[str] = None,
    pixel_id_override: Optional[str] = None,
    access_token_override: Optional[str] = None,
    test_event_code_override: Optional[str] = None,
) -> dict:
    """
    Envia evento Purchase ao Meta CAPI.
    Fire-and-forget — não bloqueia o pipeline.
    """
    pixel_id = pixel_id_override or settings.meta_pixel_id
    access_token = access_token_override or settings.meta_access_token
    test_code = test_event_code_override or settings.meta_test_event_code

    if not pixel_id or not access_token:
        logger.info(
            "Meta CAPI não configurado (META_PIXEL_ID ou META_ACCESS_TOKEN vazio) — skip"
        )
        return {"status": "skipped", "reason": "not_configured"}

    try:
        event = build_purchase_event(
            shopify_order_id, email, phone, revenue, currency, event_source_url
        )
    except ValueError as e:
        logger.warning("Meta CAPI skipped for order %s: %s", shopify_order_id, e)
        return {"status": "skipped", "reason": str(e)}

    payload: dict = {
        "data": [event],
        "access_token": access_token,
    }
    if test_code:
        payload["test_event_code"] = test_code

    url = META_CAPI_URL.format(pixel_id=pixel_id)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response_data = response.json()

        if response.status_code == 200:
            events_received = response_data.get("events_received", 0)
            fbtrace_id = response_data.get("fbtrace_id", "")
            logger.info(
                "Meta CAPI OK: order=%s, events_received=%s, fbtrace_id=%s",
                shopify_order_id,
                events_received,
                fbtrace_id,
            )
            return {
                "status": "ok",
                "events_received": events_received,
                "fbtrace_id": fbtrace_id,
                "event_id": event["event_id"],
            }

        error = response_data.get("error", {})
        logger.error(
            "Meta CAPI error: order=%s, code=%s, msg=%s",
            shopify_order_id,
            error.get("code"),
            error.get("message"),
        )
        return {"status": "error", "error": error}

    except Exception as e:
        logger.error("Meta CAPI request failed for order %s: %s", shopify_order_id, e)
        return {"status": "error", "error": str(e)}
