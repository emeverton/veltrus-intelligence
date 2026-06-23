import hashlib
import re
from enum import Enum


class SignalType(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    GCLID = "gclid"
    FBCLID = "fbclid"
    GA_CLIENT_ID = "ga_client_id"
    COOKIE_ID = "cookie_id"
    PIXEL_ID = "pixel_id"
    IP_UA_HASH = "ip_ua_hash"


DETERMINISTIC = {
    SignalType.EMAIL,
    SignalType.PHONE,
    SignalType.GCLID,
    SignalType.FBCLID,
    SignalType.GA_CLIENT_ID,
    SignalType.COOKIE_ID,
    SignalType.PIXEL_ID,
}

SIGNAL_CONFIDENCE = {
    SignalType.EMAIL: 1.0,
    SignalType.PHONE: 1.0,
    SignalType.GCLID: 1.0,
    SignalType.FBCLID: 1.0,
    SignalType.GA_CLIENT_ID: 0.95,
    SignalType.COOKIE_ID: 0.90,
    SignalType.PIXEL_ID: 0.95,
    SignalType.IP_UA_HASH: 0.60,
}


def normalize(signal_type: SignalType, value: str) -> str:
    value = value.strip()
    if signal_type == SignalType.EMAIL:
        return value.lower()
    if signal_type == SignalType.PHONE:
        return re.sub(r"\D", "", value)
    return value


def compute_hash(signal_type: SignalType, value: str) -> str:
    normalized = normalize(signal_type, value)
    raw = f"{signal_type.value}:{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()
