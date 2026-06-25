"""
Parser para response da VTEX Orders API.
Documentação: https://developers.vtex.com/docs/api-reference/orders-api

O webhook VTEX envia apenas orderId + state.
Os detalhes vêm de GET /api/oms/pvt/orders/{orderId}.
"""

PAID_STATES = {
    "payment-approved",
    "ready-to-handle",
    "handling",
    "invoiced",
    "order-accepted",
}


def is_paid_state(state: str) -> bool:
    return state.lower().replace("_", "-") in PAID_STATES


def extract_vtex_order_id(webhook_payload: dict) -> str:
    return str(
        webhook_payload.get("OrderId", "") or webhook_payload.get("orderId", "")
    )


def extract_vtex_account(webhook_payload: dict) -> str:
    origin = webhook_payload.get("Origin", {}) or {}
    return str(origin.get("Account", ""))


def parse_vtex_order_details(order: dict) -> dict:
    """Extrai sinais, UTMs e revenue do response completo da VTEX Orders API."""
    client = order.get("clientProfileData", {}) or {}
    marketing = order.get("marketingData", {}) or {}
    totals = order.get("totals", []) or []

    signals = []
    email = client.get("email")
    if email and "@" in email:
        signals.append({"type": "email", "value": email.strip().lower()})
    phone = (
        client.get("phone")
        or client.get("homePhone")
        or client.get("businessPhone")
    )
    if phone:
        signals.append({"type": "phone", "value": phone})

    utms = {
        "utm_source": marketing.get("utmSource"),
        "utm_medium": marketing.get("utmMedium"),
        "utm_campaign": marketing.get("utmCampaign"),
        "gclid": None,
        "fbclid": None,
    }

    if marketing.get("marketingTags"):
        tags = marketing.get("marketingTags", []) or []
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("gclid:"):
                utms["gclid"] = tag.replace("gclid:", "")
            elif isinstance(tag, str) and tag.startswith("fbclid:"):
                utms["fbclid"] = tag.replace("fbclid:", "")

    total_value = 0.0
    for t in totals:
        if isinstance(t, dict) and t.get("id") in ("Items", "Shipping"):
            try:
                total_value += float(t.get("value", 0)) / 100
            except (ValueError, TypeError):
                pass

    currency = order.get("storePreferencesData", {}).get("currencyCode", "BRL")

    return {
        "signals": signals,
        "utms": utms,
        "revenue": total_value,
        "currency": currency,
        "email": email,
        "phone": phone,
    }


def determine_vtex_channel(utms: dict) -> str:
    if utms.get("gclid"):
        return "google_ads"
    if utms.get("fbclid"):
        return "meta_ads"
    source = (utms.get("utm_source") or "").lower()
    medium = (utms.get("utm_medium") or "").lower()
    if "google" in source or medium in ("cpc", "ppc"):
        return "google_ads"
    if "facebook" in source or "instagram" in source or "meta" in source:
        return "meta_ads"
    if medium in ("email", "newsletter"):
        return "email"
    if medium == "organic":
        return "organic"
    return "direct"
