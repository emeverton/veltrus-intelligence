"""
Geração de mensagens personalizadas via Claude API.
Nunca usa Qwen para outreach — risco de qualidade.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

SYSTEM_EXISTING = """Você é o KAIROS, o assistente de relacionamento da Veltrus.
Gere uma mensagem de reativação CURTA e PERSONALIZADA para um cliente que não compra há mais de 30 dias.
Seja direto, humano, nunca robotizado. Sem markdown, sem emojis excessivos.
Para email: retorne JSON {"subject": "...", "body_html": "...", "body_text": "..."}.
Para WhatsApp: retorne JSON {"text": "..."} (máx 300 chars, tom conversacional).
Responda SOMENTE com o JSON, sem explicações."""

SYSTEM_COLD = """Você é o KAIROS, o assistente de relacionamento da Veltrus.
Gere uma mensagem de primeiro contato CURTA para alguém que demonstrou interesse mas não comprou.
Tom: educativo e útil, nunca pressão. Máx 1 CTA claro.
Para email: retorne JSON {"subject": "...", "body_html": "...", "body_text": "..."}.
Para WhatsApp: retorne JSON {"text": "..."} (máx 250 chars).
Responda SOMENTE com o JSON, sem explicações."""


def _parse_claude_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        parts = content.split("```")
        content = parts[1] if len(parts) > 1 else content
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content.strip())


async def generate_message(
    profile: dict,
    segment: str,
    channel: str,
    brand_context: str = "Veltrus Intelligence",
) -> dict:
    """Gera mensagem personalizada via Claude API."""
    system = SYSTEM_EXISTING if segment == "existing_customer" else SYSTEM_COLD
    ltv = float(profile.get("total_ltv") or 0)
    order_count = int(profile.get("order_count") or 0)
    days_inactive = None
    last = profile.get("last_order")
    if last:
        now = datetime.now(timezone.utc)
        if hasattr(last, "replace"):
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            days_inactive = (now - last).days

    user_prompt = f"""
Canal: {channel}
Segmento: {segment}
Contexto da marca: {brand_context}
Perfil do cliente:
  - LTV total: R$ {ltv:.2f}
  - Número de compras: {order_count}
  {"- Dias sem comprar: " + str(days_inactive) if days_inactive else "- Primeiro contato"}
  - Email disponível: {"Sim" if profile.get("email") else "Não"}
  - WhatsApp disponível: {"Sim" if profile.get("phone") else "Não"}
"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": CLAUDE_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 800,
                    "system": system,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
            response.raise_for_status()
            content = response.json()["content"][0]["text"]
            return _parse_claude_json(content)
    except Exception as exc:
        logger.error("Falha na geração de mensagem KAIROS: %s", exc)
        if channel == "email":
            return {
                "subject": f"Uma mensagem para você — {brand_context}",
                "body_html": "<p>Olá! Gostaríamos de conversar sobre como podemos ajudar você.</p>",
                "body_text": "Olá! Gostaríamos de conversar sobre como podemos ajudar você.",
            }
        return {"text": "Olá! Estamos aqui caso precise de alguma coisa."}
