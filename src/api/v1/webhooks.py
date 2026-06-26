import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import text as sql_text

from src.config import settings
from src.database import AsyncSessionFactory
from src.stores import repository as store_repo
from src.webhooks.hmac_verify import verify_shopify_hmac
from src.webhooks.shopify_handler import process_shopify_order
from src.webhooks.tray_handler import process_tray_order
from src.webhooks.tray_parser import is_paid_order
from src.webhooks.nuvemshop_handler import process_nuvemshop_order
from src.webhooks.nuvemshop_parser import (
    is_paid_order as is_nuvemshop_paid,
    extract_nuvemshop_store_id,
    extract_nuvemshop_order_id,
)
from src.webhooks.vtex_handler import process_vtex_order
from src.webhooks.vtex_parser import (
    is_paid_state,
    extract_vtex_order_id,
    extract_vtex_account,
)
from src.webhooks.woocommerce_parser import (
    verify_woocommerce_hmac,
    is_paid_order as wc_is_paid,
    extract_woocommerce_store_url,
    extract_woocommerce_order_id,
)
from src.webhooks.woocommerce_handler import process_woocommerce_order
from src.webhooks.generic_handler import process_generic_order
from src.webhooks.loja_integrada_parser import (
    is_paid_order as li_is_paid,
    extract_li_order_id,
    extract_li_store_key,
)
from src.webhooks.loja_integrada_handler import process_li_order
from src.webhooks.moovin_parser import (
    is_paid_order as moovin_is_paid,
    extract_moovin_order_id,
    extract_moovin_store_id,
)
from src.webhooks.moovin_handler import process_moovin_order
from src.webhooks.resend_events_handler import handle_resend_event, verify_resend_signature

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


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


async def _get_nuvemshop_store(store_id: str) -> dict | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            sql_text("""
                SELECT store_id, display_name, api_key,
                       meta_pixel_id, meta_access_token, meta_test_event_code, active
                FROM nuvemshop_stores
                WHERE store_id = :store_id AND active = true
            """),
            {"store_id": store_id},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None


async def _get_vtex_store(account_name: str) -> dict | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            sql_text("""
                SELECT account_name, display_name, app_key, app_token,
                       meta_pixel_id, meta_access_token, meta_test_event_code, active
                FROM vtex_stores
                WHERE account_name = :account AND active = true
            """),
            {"account": account_name},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None


@router.post("/shopify/orders/paid")
@limiter.limit("120/minute")
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
@limiter.limit("120/minute")
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


@router.post("/nuvemshop/orders")
@limiter.limit("120/minute")
async def nuvemshop_orders_webhook(request: Request):
    """
    Webhook Nuvemshop (Tienda Nube).
    Auth: Authorization: Token token=<api_key>
    Processa apenas ordens com payment_status == 'paid'.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Token token=", "").strip()

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    store_id = extract_nuvemshop_store_id(payload)
    if not store_id:
        raise HTTPException(status_code=400, detail="store_id ausente no payload")

    store = await _get_nuvemshop_store(store_id)
    if not store:
        logger.warning("Nuvemshop store_id %s não cadastrado", store_id)
        raise HTTPException(status_code=401, detail="Store not found")

    if token != store["api_key"]:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not is_nuvemshop_paid(payload):
        status = payload.get("payment_status") or payload.get("status", "?")
        logger.info("Nuvemshop order status %s — skipping", status)
        return {
            "received": True,
            "processed": False,
            "reason": f"status {status} is not paid",
        }

    order_id = extract_nuvemshop_order_id(payload)
    logger.info("Nuvemshop webhook: store=%s, order=%s", store_id, order_id)

    asyncio.create_task(process_nuvemshop_order(payload, store))
    return {"received": True, "processed": True, "order_id": str(order_id)}


@router.post("/vtex/orders")
@limiter.limit("120/minute")
async def vtex_orders_webhook(request: Request):
    """
    Webhook VTEX.
    VTEX envia apenas orderId + state → buscamos detalhes via VTEX API.
    Auth: X-VTEX-API-AppKey + X-VTEX-API-AppToken no header.
    """
    app_key = request.headers.get("X-VTEX-API-AppKey", "")
    app_token = request.headers.get("X-VTEX-API-AppToken", "")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    account_name = extract_vtex_account(payload)
    if not account_name:
        raise HTTPException(status_code=400, detail="Origin.Account ausente no payload")

    store = await _get_vtex_store(account_name)
    if not store:
        logger.warning("VTEX account %s não cadastrado", account_name)
        raise HTTPException(status_code=401, detail="Store not found")

    if app_key != store["app_key"] or app_token != store["app_token"]:
        raise HTTPException(status_code=401, detail="Invalid VTEX credentials")

    state = payload.get("State", payload.get("state", ""))
    if not is_paid_state(state):
        logger.info("VTEX state %s — skipping", state)
        return {
            "received": True,
            "processed": False,
            "reason": f"state '{state}' is not paid",
        }

    order_id = extract_vtex_order_id(payload)
    logger.info(
        "VTEX webhook: account=%s, order=%s, state=%s",
        account_name,
        order_id,
        state,
    )

    asyncio.create_task(process_vtex_order(payload, store))
    return {
        "received": True,
        "processed": True,
        "order_id": order_id,
        "state": state,
    }


async def _get_woocommerce_store(store_url: str) -> dict | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            sql_text("""
                SELECT store_url, display_name, webhook_secret,
                       meta_pixel_id, meta_access_token, meta_test_event_code,
                       google_ads_customer_id, google_ads_conversion_action, active
                FROM woocommerce_stores
                WHERE store_url = :url AND active = true
            """),
            {"url": store_url},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None


async def _resolve_woocommerce_store(store_url: str) -> dict | None:
    url = store_url.rstrip("/").lower()
    candidates = [url]
    if not url.startswith("http"):
        candidates.append(f"https://{url}")
    if url.startswith("http://"):
        candidates.append(url.replace("http://", "https://", 1))
    for candidate in candidates:
        store = await _get_woocommerce_store(candidate)
        if store:
            return store
    return None


@router.post("/woocommerce/orders")
@limiter.limit("120/minute")
async def woocommerce_orders_webhook(request: Request):
    """
    Webhook WooCommerce.
    HMAC: base64(HMAC-SHA256) no header X-WC-Webhook-Signature.
    DIFERENTE do Shopify (hex) — não reutilizar verify_shopify_hmac.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-WC-Webhook-Signature", "")
    store_url = extract_woocommerce_store_url(dict(request.headers))

    if not store_url:
        raise HTTPException(status_code=400, detail="X-WC-Webhook-Source ausente")

    store = await _resolve_woocommerce_store(store_url)
    if not store:
        logger.warning("WooCommerce store %s não cadastrado", store_url)
        raise HTTPException(status_code=401, detail="Store not found")

    if not verify_woocommerce_hmac(raw_body, store["webhook_secret"], signature):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    try:
        order = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not wc_is_paid(order):
        status = order.get("status", "?")
        return {
            "received": True,
            "processed": False,
            "reason": f"status {status} not paid",
        }

    order_id = extract_woocommerce_order_id(order)
    logger.info("WooCommerce webhook: store=%s, order=%s", store["store_url"], order_id)
    asyncio.create_task(process_woocommerce_order(order, store))
    return {"received": True, "processed": True, "order_id": order_id}


async def _get_generic_store(store_id: str) -> dict | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            sql_text("""
                SELECT store_id, display_name, api_key, platform,
                       meta_pixel_id, meta_access_token, meta_test_event_code,
                       google_ads_customer_id, google_ads_conversion_action, active
                FROM generic_stores
                WHERE store_id = :sid AND active = true
            """),
            {"sid": store_id},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None


@router.post("/generic/order")
@limiter.limit("120/minute")
async def generic_order_webhook(request: Request):
    """
    Endpoint genérico para n8n / Make / Zapier.
    Auth: X-Store-Key header com api_key da generic_stores.
    """
    api_key = request.headers.get("X-Store-Key", "")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    store_id = str(payload.get("store_id", ""))
    if not store_id:
        raise HTTPException(status_code=400, detail="store_id obrigatório no payload")

    store = await _get_generic_store(store_id)
    if not store:
        raise HTTPException(status_code=401, detail="Store not found")
    if api_key != store["api_key"]:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not payload.get("order_id"):
        raise HTTPException(status_code=400, detail="order_id obrigatório no payload")

    revenue = float(payload.get("revenue", 0))
    if revenue <= 0:
        return {"received": True, "processed": False, "reason": "revenue <= 0"}

    logger.info(
        "Generic order: store=%s, platform=%s, order=%s",
        store_id,
        payload.get("platform"),
        payload.get("order_id"),
    )
    asyncio.create_task(process_generic_order(payload, store))
    return {"received": True, "processed": True, "order_id": str(payload.get("order_id"))}


async def _get_li_store(store_key: str) -> dict | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            sql_text("""
                SELECT store_key, display_name, api_key,
                       meta_pixel_id, meta_access_token, meta_test_event_code, active
                FROM loja_integrada_stores
                WHERE store_key = :sk AND active = true
            """),
            {"sk": store_key},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None


async def _get_moovin_store(store_id: str) -> dict | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            sql_text("""
                SELECT store_id, display_name, api_key,
                       meta_pixel_id, meta_access_token, meta_test_event_code, active
                FROM moovin_stores
                WHERE store_id = :sid AND active = true
            """),
            {"sid": store_id},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None


@router.post("/loja-integrada/orders")
@limiter.limit("120/minute")
async def loja_integrada_webhook(request: Request):
    """
    Webhook Loja Integrada.
    Auth: Authorization: chave <api_key>.
    Situações processadas: 2=Aprovado, 3=Preparação, 4=Enviado, 5=Entregue.
    """
    auth = request.headers.get("Authorization", "")
    api_key = auth.replace("chave ", "").strip()

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    store_key = extract_li_store_key(payload, dict(request.headers))
    if not store_key:
        store_key = api_key

    store = await _get_li_store(store_key)
    if not store:
        logger.warning("LI store_key %s não cadastrado", store_key)
        raise HTTPException(status_code=401, detail="Store not found")

    if api_key != store["api_key"]:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not li_is_paid(payload):
        situacao = payload.get("situacao", {})
        return {
            "received": True,
            "processed": False,
            "reason": f"situacao {situacao} not paid",
        }

    order_id = extract_li_order_id(payload)
    logger.info("LI webhook: store=%s, order=%s", store_key, order_id)
    asyncio.create_task(process_li_order(payload, store))
    return {"received": True, "processed": True, "order_id": order_id}


@router.post("/moovin/orders")
@limiter.limit("120/minute")
async def moovin_webhook(request: Request):
    """
    Webhook Moovin.
    Auth: X-Store-Key ou Authorization: Token token=<api_key>.
    ATENÇÃO: verificar payload real com Moovin antes de usar em produção.
    """
    api_key = (
        request.headers.get("X-Store-Key")
        or request.headers.get("Authorization", "").replace("Token token=", "").strip()
        or ""
    )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    store_id = extract_moovin_store_id(payload) or request.headers.get(
        "X-Store-Id", ""
    )

    if not store_id:
        raise HTTPException(
            status_code=400,
            detail="store_id não encontrado no payload ou header X-Store-Id",
        )

    store = await _get_moovin_store(store_id)
    if not store:
        logger.warning("Moovin store_id %s não cadastrado", store_id)
        raise HTTPException(status_code=401, detail="Store not found")

    if api_key != store["api_key"]:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not moovin_is_paid(payload):
        return {
            "received": True,
            "processed": False,
            "reason": (
                f"status not paid (status={payload.get('status')}; "
                f"status_id={payload.get('status_id')})"
            ),
        }

    order_id = extract_moovin_order_id(payload)
    logger.info("Moovin webhook: store=%s, order=%s", store_id, order_id)
    asyncio.create_task(process_moovin_order(payload, store))
    return {"received": True, "processed": True, "order_id": order_id}


@router.post("/resend/email-events")
async def resend_email_events(request: Request):
    """
    Webhook Resend para open/click/bounce/unsubscribe.
    Configurar em resend.com → Webhooks → Add endpoint.
    """
    raw_body = await request.body()

    if not verify_resend_signature(raw_body, dict(request.headers)):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    asyncio.create_task(handle_resend_event(payload))
    return {"received": True}
