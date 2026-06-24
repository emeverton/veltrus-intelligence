"""
Admin API — gerenciamento de lojas Shopify.
Autenticado via X-Admin-Key header.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_session
from src.stores import repository as store_repo
from src.stores.schemas import StoreCreate, StoreResponse, StoreUpdate

router = APIRouter()


async def require_admin_key(
    x_admin_key: str = Header(alias="X-Admin-Key", default=""),
) -> None:
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=503,
            detail="Admin API not configured — set ADMIN_API_KEY",
        )
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")


def _to_response(store) -> StoreResponse:
    return StoreResponse(
        id=str(store.id),
        shop_domain=store.shop_domain,
        display_name=store.display_name,
        active=store.active,
        meta_pixel_id=store.meta_pixel_id,
        google_ads_customer_id=store.google_ads_customer_id,
        created_at=store.created_at,
    )


@router.get("/stores", response_model=list[StoreResponse])
async def list_stores(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    stores = await store_repo.list_stores(session)
    return [_to_response(s) for s in stores]


@router.post("/stores", response_model=StoreResponse, status_code=201)
async def create_store(
    payload: StoreCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    store = await store_repo.create_store(session, payload.model_dump())
    await session.commit()
    return _to_response(store)


@router.put("/stores/{store_id}", response_model=StoreResponse)
async def update_store(
    store_id: UUID,
    payload: StoreUpdate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    store = await store_repo.update_store(session, store_id, data)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    await session.commit()
    return _to_response(store)


@router.delete("/stores/{store_id}", status_code=204)
async def deactivate_store(
    store_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    ok = await store_repo.deactivate_store(session, store_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Store not found")
    await session.commit()
