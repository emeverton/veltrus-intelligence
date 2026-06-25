"""
Parser de payload Tray Commerce.
Tray Order webhook: enviado quando status do pedido muda para pago (status_id: 7).
"""

PAID_STATUS_IDS = {"7", "13"}


def is_paid_order(payload: dict) -> bool:
    """Verifica se o evento é de pedido pago."""
    order = payload.get("order", {})
    status = str(order.get("status_id", ""))
    return status in PAID_STATUS_IDS


def extract_tray_signals(payload: dict) -> list[dict]:
    """Extrai sinais de identidade do payload Tray."""
    order = payload.get("order", {})
    customer = order.get("customer", {})

    signals = []
    email = customer.get("email")
    if email and "@" in email:
        signals.append({"type": "email", "value": email.strip().lower()})

    phone = (
        customer.get("phone")
        or customer.get("phone_mobile")
        or customer.get("phone_commercial")
    )
    if phone:
        signals.append({"type": "phone", "value": phone})

    return signals


def extract_tray_utms(payload: dict) -> dict:
    """Extrai UTMs do payload Tray (campo utm dentro do objeto order)."""
    order = payload.get("order", {})
    utm = order.get("utm") or {}

    return {
        "utm_source": utm.get("utm_source") or None,
        "utm_medium": utm.get("utm_medium") or None,
        "utm_campaign": utm.get("utm_campaign") or None,
        "gclid": utm.get("gclid") or order.get("gclid") or None,
        "fbclid": utm.get("fbclid") or order.get("fbclid") or None,
    }


def extract_tray_revenue(payload: dict) -> tuple[float, str]:
    """Retorna (valor, moeda) da ordem Tray."""
    order = payload.get("order", {})
    try:
        value = float(
            order.get("value") or order.get("payment", {}).get("price") or "0"
        )
    except (ValueError, TypeError):
        value = 0.0
    return value, "BRL"


def extract_tray_order_id(payload: dict) -> str:
    """ID único da ordem na Tray."""
    order = payload.get("order", {})
    order_id = order.get("id") or order.get("order_id") or ""
    return str(order_id)


def extract_tray_seller_id(payload: dict) -> str:
    """ID da loja (seller) na Tray."""
    return str(payload.get("seller_id", ""))


def determine_tray_channel(utms: dict) -> str:
    """Determina canal de marketing a partir dos UTMs Tray."""
    if utms.get("gclid"):
        return "google_ads"
    if utms.get("fbclid"):
        return "meta_ads"
    source = (utms.get("utm_source") or "").lower()
    medium = (utms.get("utm_medium") or "").lower()
    if "google" in source or medium == "cpc":
        return "google_ads"
    if "facebook" in source or "instagram" in source:
        return "meta_ads"
    if medium in ("email", "newsletter"):
        return "email"
    if medium == "organic":
        return "organic"
    return "direct"
