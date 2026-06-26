"""Canais de saída do KAIROS: Resend (email) + Evolution API (WhatsApp)."""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM_EMAIL", os.getenv("RESEND_FROM", "noreply@ehos.com.br"))
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "https://api.ehos.com.br")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "veltrus-agent")


async def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    body_text: str,
    tags: list[str] | None = None,
) -> dict:
    """Envia email via Resend."""
    payload: dict = {
        "from": f"VERTEX by Veltrus <{RESEND_FROM}>",
        "to": [to_email],
        "subject": subject,
        "html": body_html,
        "text": body_text,
    }
    if tags:
        payload["tags"] = [{"name": tag} for tag in tags]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return {"id": data.get("id"), "success": True}
    except Exception as exc:
        logger.error("Falha ao enviar email KAIROS para %s: %s", to_email, exc)
        return {"id": None, "success": False, "error": str(exc)}


async def send_whatsapp(phone: str, text: str) -> dict:
    """Envia mensagem WhatsApp via Evolution API."""
    phone_clean = "".join(filter(str.isdigit, phone))
    if not phone_clean.startswith("55"):
        phone_clean = "55" + phone_clean
    wa_number = phone_clean + "@s.whatsapp.net"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}",
                headers={
                    "apikey": EVOLUTION_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"number": wa_number, "text": text},
            )
            response.raise_for_status()
            data = response.json()
            return {"id": data.get("key", {}).get("id"), "success": True}
    except Exception as exc:
        logger.error("Falha ao enviar WhatsApp KAIROS para %s: %s", phone, exc)
        return {"id": None, "success": False, "error": str(exc)}
