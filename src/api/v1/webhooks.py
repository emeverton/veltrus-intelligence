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

router = APIRouter()
logger = logging.getLogger(__name__)


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
async def recent_orders(limit: int = 10):
    """Últimas ordens recebidas via webhook."""
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            sql_text("""
                SELECT shopify_order_id, shop_domain, email, total_price, currency,
                       channel, processing_status, created_at
                FROM shopify_orders
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )
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
