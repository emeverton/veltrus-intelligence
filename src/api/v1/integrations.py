from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.config import settings
from src.integrations.meta_capi import send_purchase_event

router = APIRouter()


class MetaTestRequest(BaseModel):
    email: Optional[str] = "test@example.com"
    phone: Optional[str] = "+5511999999999"
    value: float = 100.0
    currency: str = "BRL"


@router.post("/meta/test")
async def test_meta_capi(body: MetaTestRequest | None = None):
    """
    Envia um evento de teste para o Meta CAPI.
    Usa META_TEST_EVENT_CODE se configurado (recomendado).
    Ver resultado em: Meta Events Manager → Test Events.
    """
    if not settings.meta_pixel_id:
        return {
            "status": "not_configured",
            "message": "Configure META_PIXEL_ID e META_ACCESS_TOKEN no .env do VPS",
        }

    req = body or MetaTestRequest()
    result = await send_purchase_event(
        shopify_order_id="test_event_001",
        email=req.email,
        phone=req.phone,
        revenue=req.value,
        currency=req.currency,
        event_source_url="https://loja.exemplo.com.br/test",
    )
    return result


@router.get("/meta/status")
async def meta_capi_status():
    """Verifica se Meta CAPI está configurado."""
    return {
        "pixel_id_configured": bool(settings.meta_pixel_id),
        "access_token_configured": bool(settings.meta_access_token),
        "test_event_code": settings.meta_test_event_code or None,
        "ready": bool(settings.meta_pixel_id and settings.meta_access_token),
    }


@router.post("/google/test")
async def test_google_ads(
    gclid: str = "test_gclid_123",
    customer_id: str = "",
    conversion_action: str = "",
    value: float = 100.0,
    currency: str = "BRL",
):
    """Testa upload de conversão Google Ads."""
    from src.integrations.google_ads import upload_conversion

    if not customer_id:
        return {
            "status": "not_configured",
            "message": "Informe customer_id e conversion_action",
        }
    result = await upload_conversion(
        gclid, customer_id, conversion_action, value, currency
    )
    return result


@router.get("/google/status")
async def google_ads_status():
    return {
        "developer_token_configured": bool(settings.google_ads_developer_token),
        "oauth_configured": bool(
            settings.google_ads_client_id and settings.google_ads_refresh_token
        ),
        "ready": bool(
            settings.google_ads_developer_token
            and settings.google_ads_client_id
            and settings.google_ads_refresh_token
        ),
    }
