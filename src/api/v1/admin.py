"""
Admin API — gerenciamento de lojas Shopify.
Autenticado via X-Admin-Key header.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text as sql_text
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


class TrayStoreCreate(BaseModel):
    seller_id: str
    display_name: Optional[str] = None
    api_key: str
    meta_pixel_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    google_ads_customer_id: Optional[str] = None


@router.get("/tray-stores")
async def list_tray_stores(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    result = await session.execute(
        sql_text("""
            SELECT seller_id, display_name, meta_pixel_id, google_ads_customer_id,
                   active, created_at
            FROM tray_stores
            ORDER BY created_at DESC
        """)
    )
    return [dict(r._mapping) for r in result.fetchall()]


@router.post("/tray-stores", status_code=201)
async def create_tray_store(
    payload: TrayStoreCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    import uuid

    await session.execute(
        sql_text("""
            INSERT INTO tray_stores
                (id, seller_id, display_name, api_key, meta_pixel_id,
                 meta_access_token, google_ads_customer_id)
            VALUES
                (:id, :seller_id, :display_name, :api_key, :meta_pixel_id,
                 :meta_access_token, :google_ads_customer_id)
            ON CONFLICT (seller_id) DO UPDATE SET
              api_key = EXCLUDED.api_key,
              display_name = EXCLUDED.display_name,
              meta_pixel_id = EXCLUDED.meta_pixel_id,
              meta_access_token = EXCLUDED.meta_access_token,
              google_ads_customer_id = EXCLUDED.google_ads_customer_id
        """),
        {
            "id": str(uuid.uuid4()),
            "seller_id": payload.seller_id,
            "display_name": payload.display_name,
            "api_key": payload.api_key,
            "meta_pixel_id": payload.meta_pixel_id,
            "meta_access_token": payload.meta_access_token,
            "google_ads_customer_id": payload.google_ads_customer_id,
        },
    )
    await session.commit()
    return {"seller_id": payload.seller_id, "created": True}


class NuvemshopStoreCreate(BaseModel):
    store_id: str
    display_name: Optional[str] = None
    api_key: str
    meta_pixel_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    google_ads_customer_id: Optional[str] = None


@router.get("/nuvemshop-stores")
async def list_nuvemshop_stores(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    result = await session.execute(
        sql_text("""
            SELECT store_id, display_name, meta_pixel_id, google_ads_customer_id,
                   active, created_at
            FROM nuvemshop_stores
            ORDER BY created_at DESC
        """)
    )
    return [dict(r._mapping) for r in result.fetchall()]


@router.post("/nuvemshop-stores", status_code=201)
async def create_nuvemshop_store(
    payload: NuvemshopStoreCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    import uuid

    await session.execute(
        sql_text("""
            INSERT INTO nuvemshop_stores
                (id, store_id, display_name, api_key, meta_pixel_id,
                 meta_access_token, google_ads_customer_id)
            VALUES
                (:id, :store_id, :display_name, :api_key, :meta_pixel_id,
                 :meta_access_token, :google_ads_customer_id)
            ON CONFLICT (store_id) DO UPDATE SET
              api_key = EXCLUDED.api_key,
              display_name = EXCLUDED.display_name,
              meta_pixel_id = EXCLUDED.meta_pixel_id,
              meta_access_token = EXCLUDED.meta_access_token,
              google_ads_customer_id = EXCLUDED.google_ads_customer_id
        """),
        {
            "id": str(uuid.uuid4()),
            "store_id": payload.store_id,
            "display_name": payload.display_name,
            "api_key": payload.api_key,
            "meta_pixel_id": payload.meta_pixel_id,
            "meta_access_token": payload.meta_access_token,
            "google_ads_customer_id": payload.google_ads_customer_id,
        },
    )
    await session.commit()
    return {"store_id": payload.store_id, "created": True}


class VtexStoreCreate(BaseModel):
    account_name: str
    display_name: Optional[str] = None
    app_key: str
    app_token: str
    meta_pixel_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    google_ads_customer_id: Optional[str] = None


@router.get("/vtex-stores")
async def list_vtex_stores(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    result = await session.execute(
        sql_text("""
            SELECT account_name, display_name, meta_pixel_id, google_ads_customer_id,
                   active, created_at
            FROM vtex_stores
            ORDER BY created_at DESC
        """)
    )
    return [dict(r._mapping) for r in result.fetchall()]


@router.post("/vtex-stores", status_code=201)
async def create_vtex_store(
    payload: VtexStoreCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    import uuid

    await session.execute(
        sql_text("""
            INSERT INTO vtex_stores
                (id, account_name, display_name, app_key, app_token, meta_pixel_id,
                 meta_access_token, google_ads_customer_id)
            VALUES
                (:id, :account_name, :display_name, :app_key, :app_token, :meta_pixel_id,
                 :meta_access_token, :google_ads_customer_id)
            ON CONFLICT (account_name) DO UPDATE SET
                app_key = EXCLUDED.app_key,
                app_token = EXCLUDED.app_token,
                display_name = EXCLUDED.display_name,
                meta_pixel_id = EXCLUDED.meta_pixel_id,
                meta_access_token = EXCLUDED.meta_access_token,
                google_ads_customer_id = EXCLUDED.google_ads_customer_id
        """),
        {
            "id": str(uuid.uuid4()),
            "account_name": payload.account_name,
            "display_name": payload.display_name,
            "app_key": payload.app_key,
            "app_token": payload.app_token,
            "meta_pixel_id": payload.meta_pixel_id,
            "meta_access_token": payload.meta_access_token,
            "google_ads_customer_id": payload.google_ads_customer_id,
        },
    )
    await session.commit()
    return {"account_name": payload.account_name, "created": True}


class WooCommerceStoreCreate(BaseModel):
    store_url: str
    display_name: Optional[str] = None
    webhook_secret: str
    consumer_key: Optional[str] = None
    consumer_secret: Optional[str] = None
    meta_pixel_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    google_ads_customer_id: Optional[str] = None


class GenericStoreCreate(BaseModel):
    store_id: str
    display_name: Optional[str] = None
    api_key: str
    platform: str = "other"
    meta_pixel_id: Optional[str] = None
    meta_access_token: Optional[str] = None


@router.get("/woocommerce-stores")
async def list_woocommerce_stores(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    result = await session.execute(
        sql_text("""
            SELECT store_url, display_name, meta_pixel_id, active, created_at
            FROM woocommerce_stores
            ORDER BY created_at DESC
        """)
    )
    return [dict(r._mapping) for r in result.fetchall()]


@router.post("/woocommerce-stores", status_code=201)
async def create_woocommerce_store(
    payload: WooCommerceStoreCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    import uuid

    url = payload.store_url.rstrip("/").lower()
    if not url.startswith("http"):
        url = f"https://{url}"

    await session.execute(
        sql_text("""
            INSERT INTO woocommerce_stores
                (id, store_url, display_name, webhook_secret, consumer_key,
                 consumer_secret, meta_pixel_id, meta_access_token,
                 google_ads_customer_id)
            VALUES (:id, :url, :name, :secret, :ckey, :csecret, :pixel, :token, :gadscid)
            ON CONFLICT (store_url) DO UPDATE SET
                webhook_secret = EXCLUDED.webhook_secret,
                display_name = EXCLUDED.display_name,
                consumer_key = EXCLUDED.consumer_key,
                consumer_secret = EXCLUDED.consumer_secret,
                meta_pixel_id = EXCLUDED.meta_pixel_id,
                meta_access_token = EXCLUDED.meta_access_token,
                google_ads_customer_id = EXCLUDED.google_ads_customer_id
        """),
        {
            "id": str(uuid.uuid4()),
            "url": url,
            "name": payload.display_name,
            "secret": payload.webhook_secret,
            "ckey": payload.consumer_key,
            "csecret": payload.consumer_secret,
            "pixel": payload.meta_pixel_id,
            "token": payload.meta_access_token,
            "gadscid": payload.google_ads_customer_id,
        },
    )
    await session.commit()
    return {"store_url": url, "created": True}


@router.get("/generic-stores")
async def list_generic_stores(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    result = await session.execute(
        sql_text("""
            SELECT store_id, display_name, platform, meta_pixel_id, active, created_at
            FROM generic_stores
            ORDER BY created_at DESC
        """)
    )
    return [dict(r._mapping) for r in result.fetchall()]


@router.post("/generic-stores", status_code=201)
async def create_generic_store(
    payload: GenericStoreCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin_key),
):
    import uuid

    await session.execute(
        sql_text("""
            INSERT INTO generic_stores
                (id, store_id, display_name, api_key, platform,
                 meta_pixel_id, meta_access_token)
            VALUES (:id, :sid, :name, :key, :platform, :pixel, :token)
            ON CONFLICT (store_id) DO UPDATE SET
                api_key = EXCLUDED.api_key,
                display_name = EXCLUDED.display_name,
                platform = EXCLUDED.platform,
                meta_pixel_id = EXCLUDED.meta_pixel_id,
                meta_access_token = EXCLUDED.meta_access_token
        """),
        {
            "id": str(uuid.uuid4()),
            "sid": payload.store_id,
            "name": payload.display_name,
            "key": payload.api_key,
            "platform": payload.platform,
            "pixel": payload.meta_pixel_id,
            "token": payload.meta_access_token,
        },
    )
    await session.commit()
    return {
        "store_id": payload.store_id,
        "platform": payload.platform,
        "created": True,
    }
