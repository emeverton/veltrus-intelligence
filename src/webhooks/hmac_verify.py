import base64
import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


def verify_shopify_hmac(
    raw_body: bytes,
    secret: str,
    signature_header: str,
) -> bool:
    """
    Verifica assinatura HMAC-SHA256 do Shopify.

    CRÍTICO: raw_body deve ser os bytes crus do request ANTES de qualquer parsing.
    Qualquer modificação no body (JSON parse, reformatação) invalida o HMAC.
    """
    if not secret:
        logger.warning("SHOPIFY_WEBHOOK_SECRET não configurado — aceitando sem verificação")
        return True

    if not signature_header:
        logger.error("Webhook sem header X-Shopify-Hmac-Sha256")
        return False

    computed = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    valid = hmac.compare_digest(computed, signature_header)
    if not valid:
        logger.warning(
            "HMAC inválido. Expected: %s... Got: %s...",
            computed[:10],
            signature_header[:10],
        )
    return valid
