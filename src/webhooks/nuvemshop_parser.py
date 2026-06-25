"""
Parser de payload Nuvemshop (Tienda Nube).
"""
from urllib.parse import parse_qs, urlparse

PAID_STATUSES = {"paid"}


def is_paid_order(payload: dict) -> bool:
    payment_status = payload.get("payment_status", "") or ""
    status = payload.get("status", "") or ""
    return payment_status.lower() in PAID_STATUSES or status.lower() == "paid"


def extract_nuvemshop_store_id(payload: dict) -> str:
    return str(payload.get("store_id", ""))


def extract_nuvemshop_order_id(payload: dict) -> str:
    return str(payload.get("id", ""))


def extract_nuvemshop_signals(payload: dict) -> list[dict]:
    signals = []
    email = payload.get("contact_email") or payload.get("billing_address", {}).get("email")
    if email and "@" in email:
        signals.append({"type": "email", "value": email.strip().lower()})
    phone = payload.get("contact_phone") or payload.get("billing_address", {}).get("phone")
    if phone:
        signals.append({"type": "phone", "value": phone})
    return signals


def _extract_utms_from_url(url: str) -> dict:
    if not url:
        return {}
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        return {
            "utm_source": qs.get("utm_source", [None])[0],
            "utm_medium": qs.get("utm_medium", [None])[0],
            "utm_campaign": qs.get("utm_campaign", [None])[0],
            "gclid": qs.get("gclid", [None])[0],
            "fbclid": qs.get("fbclid", [None])[0],
        }
    except Exception:
        return {}


def extract_nuvemshop_utms(payload: dict) -> dict:
    landing = payload.get("landing_url") or payload.get("checkout_enabled_url") or ""
    utms = _extract_utms_from_url(landing)
    if not any(utms.values()):
        origins = payload.get("origins") or []
        if origins and isinstance(origins, list):
            first = origins[0] if isinstance(origins[0], dict) else {}
            utms = {
                "utm_source": first.get("utm_source") or first.get("source"),
                "utm_medium": first.get("utm_medium") or first.get("medium"),
                "utm_campaign": first.get("utm_campaign") or first.get("campaign"),
                "gclid": first.get("gclid"),
                "fbclid": first.get("fbclid"),
            }
    return utms


def extract_nuvemshop_revenue(payload: dict) -> tuple[float, str]:
    try:
        total = float(payload.get("total") or "0")
    except (ValueError, TypeError):
        total = 0.0
    currency = (payload.get("currency") or "BRL").upper()
    return total, currency


def determine_nuvemshop_channel(utms: dict) -> str:
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
    if medium == "organic" or source == "organic":
        return "organic"
    return "direct"
