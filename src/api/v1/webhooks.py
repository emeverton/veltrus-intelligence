import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text as sql_text

from src.config import settings
from src.database import AsyncSessionFactory
from src.stores import repository as store_repo
from src.webhooks.hmac_verify import verify_shopify_hmac
from src.webhooks.shopify_handler import process_shopify_order
from src.webhooks.tray_handler import process_tray_order
from src.webhooks.tray_parser import is_paid_order

router = APIRouter()
logger = logging.getLogger(__name__)


async def _get_tray_store(seller_id: str) -> dict | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            sql_text("""
                SELECT seller_id, display_name, api_key, meta_pixel_id,
                       meta_access_token, meta_test_event_code, active
                FROM tray_stores
                WHERE seller_id = :seller_id AND active = true
            """),
            {"seller_id": seller_id},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None


@router.post("/shopify/orders/paid")
async def shopify_orders_paid(request: Request):
    """
    Webhook multi-tenant.
    Roteia pelo header X-Shopify-Shop-Domain → busca secret no banco.
    Fallback: SHOPIFY_WEBHOOK_SECRET do .env (backward compat / dev mode).
    """
    raw_body = await request.body()
    shop_domain = request.headers.get("X-Shopify-Shop-Domain", "")
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")

    store = None
    secret = settings.shopify_webhook_secret

    if shop_domain:
        async with AsyncSessionFactory() as session:
            store = await store_repo.get_by_domain(session, shop_domain)
        if store:
            secret = store.webhook_secret

    if not verify_shopify_hmac(raw_body, secret, hmac_header):
        logger.warning("HMAC inválido: domain=%s", shop_domain)
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    try:
        order = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    order["_shop_domain"] = shop_domain
    order["_store"] = store

    shopify_order_id = str(order.get("id", "unknown"))
    logger.info(
        "Webhook OK: domain=%s, order=%s, total=%s",
        shop_domain,
        shopify_order_id,
        order.get("total_price"),
    )

    asyncio.create_task(process_shopify_order(order))

    return {
        "received": True,
        "order_id": shopify_order_id,
        "shop_domain": shop_domain,
    }


@router.get("/shopify/recent")
async def recent_orders(
    limit: int = 10,
    shop_domain: str | None = None,
):
    """Últimas ordens recebidas via webhook."""
    query = """
        SELECT shopify_order_id, shop_domain, email, total_price, currency,
               channel, processing_status, created_at
        FROM shopify_orders
    """
    params: dict = {"limit": limit}
    if shop_domain:
        query += " WHERE shop_domain = :shop_domain"
        params["shop_domain"] = shop_domain
    query += " ORDER BY created_at DESC LIMIT :limit"

    async with AsyncSessionFactory() as session:
        result = await session.execute(sql_text(query), params)
        rows = result.fetchall()

    return {
        "orders": [
            {
                "shopify_order_id": r.shopify_order_id,
                "shop_domain": r.shop_domain,
                "email": r.email[:3] + "***" if r.email else None,
                "total_price": r.total_price,
                "currency": r.currency,
                "channel": r.channel,
                "status": r.processing_status,
                "received_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.post("/tray/orders")
async def tray_orders_webhook(request: Request):
    """
    Webhook Tray Commerce.
    Auth: Authorization: Token token=<api_key>
    Processa apenas ordens com status pago (status_id: 7 ou 13).
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Token token=", "").strip()

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    seller_id = str(payload.get("seller_id", ""))
    if not seller_id:
        raise HTTPException(status_code=400, detail="seller_id ausente no payload")

    store = await _get_tray_store(seller_id)
    if not store:
        logger.warning("Tray seller_id %s não cadastrado", seller_id)
        raise HTTPException(status_code=401, detail="Store not found")

    if token != store["api_key"]:
        logger.warning("Tray auth failed for seller %s", seller_id)
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not is_paid_order(payload):
        status_id = payload.get("order", {}).get("status_id", "?")
        logger.info("Tray order status %s — skipping (not paid)", status_id)
        return {
            "received": True,
            "processed": False,
            "reason": f"status_id {status_id} is not paid",
        }

    order_id = payload.get("order", {}).get("id", "unknown")
    logger.info("Tray webhook: seller=%s, order=%s", seller_id, order_id)

    asyncio.create_task(process_tray_order(payload, store))
    return {"received": True, "processed": True, "order_id": str(order_id)}
