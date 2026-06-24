"""
Extração de sinais de identidade e metadados de atribuição de uma ordem Shopify.
"""
from urllib.parse import parse_qs, urlparse


def extract_signals(order: dict) -> list[dict]:
    """
    Extrai sinais de identidade da ordem:
    email, phone (determinísticos, confidence=1.0).
    """
    signals = []
    email = order.get("email") or order.get("customer", {}).get("email")
    if email and "@" in email:
        signals.append({"type": "email", "value": email.strip().lower()})

    phone = (
        order.get("phone")
        or order.get("billing_address", {}).get("phone")
        or order.get("customer", {}).get("phone")
    )
    if phone:
        signals.append({"type": "phone", "value": phone})

    return signals


def extract_utms(order: dict) -> dict:
    """
    Extrai parâmetros UTM e tracking IDs da landing_site do Shopify.
    landing_site contém a URL completa com query params.
    """
    landing = order.get("landing_site") or order.get("landing_site_ref") or ""
    parsed = urlparse(landing)
    params = parse_qs(parsed.query)

    def first(key: str) -> str | None:
        vals = params.get(key, [])
        return vals[0] if vals else None

    return {
        "utm_source": first("utm_source"),
        "utm_medium": first("utm_medium"),
        "utm_campaign": first("utm_campaign"),
        "utm_term": first("utm_term"),
        "utm_content": first("utm_content"),
        "gclid": first("gclid"),
        "fbclid": first("fbclid"),
        "referring_site": order.get("referring_site"),
        "landing_site": landing,
    }


def determine_channel(utms: dict) -> str:
    """
    Determina o canal de marketing a partir dos UTMs.
    Ordem de prioridade: GCLID > FBCLID > UTM source/medium > referring_site > direct.
    """
    if utms.get("gclid"):
        return "google_ads"
    if utms.get("fbclid"):
        return "meta_ads"

    source = (utms.get("utm_source") or "").lower()
    medium = (utms.get("utm_medium") or "").lower()

    if "google" in source or medium == "cpc":
        return "google_ads"
    if "facebook" in source or "instagram" in source or "ig" in source:
        return "meta_ads"
    if "tiktok" in source:
        return "tiktok_ads"
    if medium in ("email", "e-mail", "newsletter"):
        return "email"
    if medium == "organic" or source == "google":
        return "organic"
    if utms.get("referring_site"):
        ref = utms["referring_site"].lower()
        if "google" in ref:
            return "organic"
        if "facebook" in ref or "instagram" in ref:
            return "organic_social"

    return "direct"


def extract_revenue(order: dict) -> tuple[float, str]:
    """Retorna (total_price: float, currency: str)."""
    try:
        price = float(order.get("total_price") or "0")
    except (ValueError, TypeError):
        price = 0.0
    currency = order.get("currency") or "BRL"
    return price, currency


def extract_line_items(order: dict) -> list[dict]:
    """Extrai resumo dos itens da ordem."""
    items = order.get("line_items", [])
    return [
        {
            "product_id": str(item.get("product_id", "")),
            "title": item.get("title", ""),
            "quantity": item.get("quantity", 1),
            "price": float(item.get("price") or "0"),
        }
        for item in items
    ]
