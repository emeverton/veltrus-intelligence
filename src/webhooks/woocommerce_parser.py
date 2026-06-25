"""
Parser WooCommerce.

DIFERENÇA CRÍTICA vs Shopify:
- Shopify HMAC: hex(HMAC-SHA256)
- WooCommerce HMAC: base64(HMAC-SHA256)

Não usar verify_shopify_hmac aqui.
"""
import base64
import hashlib
import hmac as hmac_lib

PAID_STATUSES = {"processing", "completed"}


def verify_woocommerce_hmac(raw_body: bytes, secret: str, signature: str) -> bool:
    """
    WooCommerce usa HMAC-SHA256 com output em base64.
    Header: X-WC-Webhook-Signature
    """
    if not secret:
        return True
    mac = hmac_lib.new(secret.encode("utf-8"), raw_body, hashlib.sha256)
    expected = base64.b64encode(mac.digest()).decode("utf-8")
    return hmac_lib.compare_digest(expected, signature)


def is_paid_order(order: dict) -> bool:
    return order.get("status", "") in PAID_STATUSES


def extract_woocommerce_store_url(request_headers: dict) -> str:
    """WooCommerce envia X-WC-Webhook-Source com a URL da loja."""
    source = (
        request_headers.get("x-wc-webhook-source")
        or request_headers.get("X-WC-Webhook-Source")
        or request_headers.get("x-forwarded-host")
        or request_headers.get("X-Forwarded-Host")
        or ""
    )
    return source.rstrip("/")


def extract_woocommerce_order_id(order: dict) -> str:
    return str(order.get("id", ""))


def extract_woocommerce_signals(order: dict) -> list[dict]:
    billing = order.get("billing", {}) or {}
    signals = []
    email = billing.get("email")
    if email and "@" in email:
        signals.append({"type": "email", "value": email.strip().lower()})
    phone = billing.get("phone")
    if phone:
        signals.append({"type": "phone", "value": phone})
    return signals


def extract_woocommerce_utms(order: dict) -> dict:
    meta = {}
    for item in order.get("meta_data", []):
        key = item.get("key", "")
        value = item.get("value")
        if value and isinstance(value, str):
            meta[key] = value

    utm_map = {
        "utm_source": [
            "utm_source",
            "_utm_source",
            "_ga_utm_source",
            "woo_utm_source",
            "tracking_utm_source",
        ],
        "utm_medium": [
            "utm_medium",
            "_utm_medium",
            "_ga_utm_medium",
            "woo_utm_medium",
            "tracking_utm_medium",
        ],
        "utm_campaign": [
            "utm_campaign",
            "_utm_campaign",
            "_ga_utm_campaign",
            "woo_utm_campaign",
            "tracking_utm_campaign",
        ],
        "gclid": ["gclid", "_gclid", "_ga_gclid", "woo_gclid"],
        "fbclid": ["fbclid", "_fbclid", "woo_fbclid"],
    }

    result = {}
    for param, keys in utm_map.items():
        for key in keys:
            if meta.get(key):
                result[param] = meta[key]
                break
        else:
            result[param] = None
    return result


def extract_woocommerce_revenue(order: dict) -> tuple[float, str]:
    try:
        total = float(order.get("total") or "0")
    except (ValueError, TypeError):
        total = 0.0
    currency = order.get("currency", "BRL").upper()
    return total, currency


def determine_channel(utms: dict) -> str:
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
