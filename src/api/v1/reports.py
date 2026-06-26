"""
Endpoints de relatórios — read-only, requer X-Admin-Key.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.v1.admin import require_admin_key
from src.reports.aggregator import (
    PLATFORM_MAP,
    get_all_active_stores_metrics,
    get_weekly_metrics,
)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/weekly")
async def weekly_store_report(
    platform: str = Query(
        ...,
        description="shopify|tray|nuvemshop|vtex|woocommerce|loja_integrada|moovin|generic",
    ),
    store_identifier: str = Query(..., description="Identificador da loja na plataforma"),
    weeks_back: int = Query(
        1, ge=1, le=52, description="1=semana passada, 2=duas semanas atrás..."
    ),
    _: None = Depends(require_admin_key),
):
    """
    Retorna métricas semanais de uma loja específica.
    Compara semana atual vs semana anterior.
    """
    if platform not in PLATFORM_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Plataforma inválida: {platform}. Válidas: {list(PLATFORM_MAP.keys())}",
        )

    metrics = await get_weekly_metrics(platform, store_identifier, weeks_back)
    if metrics is None:
        raise HTTPException(status_code=404, detail="Loja não encontrada ou sem dados")

    return metrics


@router.get("/weekly/all-stores")
async def weekly_all_stores_report(
    weeks_back: int = Query(1, ge=1, le=52),
    _: None = Depends(require_admin_key),
):
    """
    Retorna métricas de TODAS as lojas com atividade na semana.
    Usado pelo n8n para disparar relatórios individuais.
    """
    results = await get_all_active_stores_metrics(weeks_back)
    return {
        "stores": results,
        "total": len(results),
        "weeks_back": weeks_back,
    }
