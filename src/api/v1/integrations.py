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
