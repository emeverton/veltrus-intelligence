"""
Parser Moovin.
Usado pela Malhas e Tramas (store ID: a24f51bc-5c08-4b7e-ba3c-51fdd4d5d24b).

ATENÇÃO: Este parser foi construído com base em padrões inferidos.
Verificar com o payload real antes do deploy em produção.
Capturar payload real em: webhook.site → configurar na Moovin → fazer ordem de teste.

Campos inferidos do site malhasetramas.com.br:
- URLs de assets: storage.moovin.store/main/{store_uuid}/...
- Estrutura típica de plataformas BR similares ao Nuvemshop/Tray
"""

PAID_STATUSES = {
    "aprovado",
    "aprovada",
    "approved",
    "paid",
    "payment_approved",
    "completo",
    "completed",
    "processando",
    "processing",
}

PAID_STATUS_CODES = {"2", "3", "4", "5", 2, 3, 4, 5}


def is_paid_order(payload: dict) -> bool:
    """
    Moovin pode usar status por string ou código numérico.
    Verificar com payload real e ajustar se necessário.
    """
    status = str(
        payload.get("status", "") or payload.get("order_status", "") or ""
    ).lower()
    if status in PAID_STATUSES:
        return True
    status_id = payload.get("status_id") or payload.get("situacao_id")
    if status_id is not None:
        return str(status_id) in {str(c) for c in PAID_STATUS_CODES}
    payment_status = str(payload.get("payment_status", "") or "").lower()
    return payment_status in ("paid", "approved", "aprovado")


def extract_moovin_store_id(payload: dict) -> str:
    """Store ID pode vir no payload como store_id, seller_id, ou loja_id."""
    return str(
        payload.get("store_id")
        or payload.get("seller_id")
        or payload.get("loja_id")
        or payload.get("storeId")
        or ""
    )


def extract_moovin_order_id(payload: dict) -> str:
    return str(
        payload.get("id")
        or payload.get("order_id")
        or payload.get("orderId")
        or payload.get("numero")
        or ""
    )


def extract_moovin_signals(payload: dict) -> list[dict]:
    """Estrutura de cliente pode variar. Tentar múltiplos campos."""
    signals = []

    email = (
        payload.get("email")
        or (payload.get("customer") or {}).get("email")
        or (payload.get("cliente") or {}).get("email")
        or (payload.get("billing") or {}).get("email")
        or (payload.get("buyer") or {}).get("email")
    )
    if email and "@" in email:
        signals.append({"type": "email", "value": email.strip().lower()})

    phone = (
        payload.get("phone")
        or payload.get("telefone")
        or (payload.get("customer") or {}).get("phone")
        or (payload.get("customer") or {}).get("telefone")
        or (payload.get("cliente") or {}).get("fone")
        or (payload.get("billing") or {}).get("phone")
    )
    if phone:
        signals.append({"type": "phone", "value": str(phone)})

    return signals


def extract_moovin_utms(payload: dict) -> dict:
    """UTMs podem estar em utm, marketing, tracking, ou campos diretos."""
    utm_container = (
        payload.get("utm") or payload.get("marketing") or payload.get("tracking") or {}
    )
    if not isinstance(utm_container, dict):
        utm_container = {}

    return {
        "utm_source": utm_container.get("utm_source") or payload.get("utm_source"),
        "utm_medium": utm_container.get("utm_medium") or payload.get("utm_medium"),
        "utm_campaign": utm_container.get("utm_campaign")
        or payload.get("utm_campaign"),
        "gclid": utm_container.get("gclid") or payload.get("gclid"),
        "fbclid": utm_container.get("fbclid") or payload.get("fbclid"),
    }


def extract_moovin_revenue(payload: dict) -> tuple[float, str]:
    total = (
        payload.get("total")
        or payload.get("value")
        or payload.get("valor_total")
        or payload.get("grand_total")
        or 0
    )
    try:
        total = float(total)
    except (ValueError, TypeError):
        total = 0.0

    currency = (payload.get("currency") or payload.get("moeda") or "BRL").upper()
    return total, currency
