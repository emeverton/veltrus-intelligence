import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text as sql_text

from src.config import settings
from src.webhooks.hmac_verify import verify_shopify_hmac
from src.webhooks.shopify_handler import process_shopify_order

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/shopify/orders/paid")
async def shopify_orders_paid(request: Request):
    """
    Webhook Shopify para orders/paid.
    Responde 200 em < 1s — processamento é assíncrono.
    """
    raw_body = await request.body()

    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
    if not verify_shopify_hmac(raw_body, settings.shopify_webhook_secret, hmac_header):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    try:
        order = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    shopify_order_id = str(order.get("id", "unknown"))
    logger.info(
        "Shopify webhook received: order %s, total=%s",
        shopify_order_id,
        order.get("total_price"),
    )

    asyncio.create_task(process_shopify_order(order))

    return {"received": True, "order_id": shopify_order_id}


@router.get("/shopify/recent")
async def recent_orders(limit: int = 10):
    """Últimas ordens recebidas via webhook."""
    from src.database import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            sql_text("""
                SELECT shopify_order_id, email, total_price, currency,
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
