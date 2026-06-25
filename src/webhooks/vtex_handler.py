"""
Handler VTEX Commerce.
Fluxo: webhook (orderId + state) → VTEX API (detalhes) → identity → attribution → graph.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import text as sql_text

from src.attribution import repository as attr_repo
from src.attribution.models_math import Touchpoint, run_all_sync_models
from src.database import AsyncSessionFactory
from src.graphs.revenue_graph import sync_attribution_to_graph
from src.identity.resolver import resolve as resolve_identity
from src.nats_client import publish
from src.webhooks.tray_handler import check_usage_limit
from src.webhooks.vtex_parser import (
    determine_vtex_channel,
    extract_vtex_order_id,
    parse_vtex_order_details,
)

logger = logging.getLogger(__name__)
SHAPLEY_SUBJECT = "attribution.shapley.compute"
VTEX_ORDERS_API = (
    "https://{account}.vtexcommercestable.com.br/api/oms/pvt/orders/{order_id}"
)


async def fetch_vtex_order(
    account_name: str, order_id: str, app_key: str, app_token: str
) -> dict | None:
    """Busca detalhes completos do pedido via VTEX Orders API."""
    url = VTEX_ORDERS_API.format(account=account_name, order_id=order_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                url,
                headers={
                    "X-VTEX-API-AppKey": app_key,
                    "X-VTEX-API-AppToken": app_token,
                    "Accept": "application/json",
                },
            )
            if r.status_code == 200:
                return r.json()
            logger.error(
                "VTEX API %s for order %s: %s",
                r.status_code,
                order_id,
                r.text[:200],
            )
            return None
    except Exception as e:
        logger.error("VTEX API request failed for %s: %s", order_id, e)
        return None


async def process_vtex_order(webhook_payload: dict, store: dict) -> None:
    try:
        await _process_vtex_order_inner(webhook_payload, store)
    except Exception:
        logger.exception(
            "Failed to process VTEX order %s",
            extract_vtex_order_id(webhook_payload),
        )


async def _process_vtex_order_inner(webhook_payload: dict, store: dict) -> None:
    vtex_order_id = extract_vtex_order_id(webhook_payload)
    account_name = store["account_name"]

    if not vtex_order_id:
        logger.error("VTEX webhook sem OrderId")
        return

    logger.info("Processing VTEX order %s from %s", vtex_order_id, account_name)

    async with AsyncSessionFactory() as session:
        existing = await session.execute(
            sql_text("SELECT id FROM vtex_orders WHERE vtex_order_id = :oid"),
            {"oid": vtex_order_id},
        )
        if existing.fetchone():
            logger.info("VTEX order %s already processed", vtex_order_id)
            return

        within_limit, count = await check_usage_limit(account_name, "vtex")
        if not within_limit:
            logger.warning(
                "VTEX account %s exceeded limit (%s)", account_name, count
            )
            await _save_vtex_order(
                session,
                vtex_order_id,
                account_name,
                None,
                None,
                None,
                0,
                "BRL",
                "limit_exceeded",
            )
            await session.commit()
            return

    order_details_raw = await fetch_vtex_order(
        account_name,
        vtex_order_id,
        store["app_key"],
        store["app_token"],
    )
    if not order_details_raw:
        logger.error("VTEX order details not found for %s", vtex_order_id)
        async with AsyncSessionFactory() as session:
            await _save_vtex_order(
                session,
                vtex_order_id,
                account_name,
                None,
                None,
                None,
                0,
                "BRL",
                "fetch_failed",
            )
            await session.commit()
        return

    parsed = parse_vtex_order_details(order_details_raw)
    signals = parsed["signals"]
    utms = parsed["utms"]
    revenue = parsed["revenue"]
    currency = parsed["currency"]
    channel = determine_vtex_channel(utms)

    async with AsyncSessionFactory() as session:
        if not signals:
            logger.warning("VTEX order %s sem sinais de identidade", vtex_order_id)
            await _save_vtex_order(
                session,
                vtex_order_id,
                account_name,
                None,
                None,
                channel,
                revenue,
                currency,
                "no_signals",
                email=parsed.get("email"),
                phone=parsed.get("phone"),
            )
            await session.commit()
            return

        identity_result = await resolve_identity(session, signals, source="vtex")
        profile_id = UUID(identity_result["profile_id"])

        if any([utms.get("utm_source"), utms.get("gclid"), utms.get("fbclid")]):
            await attr_repo.ingest_touchpoint(
                session,
                profile_id=profile_id,
                channel=channel,
                touchpoint_type="purchase",
                campaign_id=utms.get("utm_campaign"),
                source=utms.get("utm_source"),
                medium=utms.get("utm_medium"),
                gclid=utms.get("gclid"),
                fbclid=utms.get("fbclid"),
                metadata={
                    "vtex_order_id": vtex_order_id,
                    "account": account_name,
                },
            )

        conversion = await attr_repo.create_conversion(
            session,
            profile_id=profile_id,
            revenue=revenue,
            currency=currency,
            metadata={
                "vtex_order_id": vtex_order_id,
                "account": account_name,
                "channel": channel,
            },
        )

        await _save_vtex_order(
            session,
            vtex_order_id,
            account_name,
            profile_id,
            conversion.id,
            channel,
            revenue,
            currency,
            "done",
            email=parsed.get("email"),
            phone=parsed.get("phone"),
        )
        await session.commit()

    asyncio.create_task(
        _compute_vtex_attribution(profile_id, conversion.id, revenue, currency)
    )

    if store.get("meta_pixel_id") and store.get("meta_access_token"):
        from src.integrations.meta_capi import send_purchase_event

        asyncio.create_task(
            send_purchase_event(
                shopify_order_id=f"vtex_{vtex_order_id}",
                email=parsed.get("email"),
                phone=parsed.get("phone"),
                revenue=revenue,
                currency=currency,
                pixel_id_override=store.get("meta_pixel_id"),
                access_token_override=store.get("meta_access_token"),
                test_event_code_override=store.get("meta_test_event_code"),
            )
        )


async def _compute_vtex_attribution(
    profile_id: UUID, conversion_id: UUID, revenue: float, currency: str
) -> None:
    try:
        async with AsyncSessionFactory() as session:
            touchpoints_db = await attr_repo.get_touchpoints_for_profile(
                session, profile_id
            )
            if not touchpoints_db:
                return
            tp_list = [
                Touchpoint(
                    channel=t.channel,
                    campaign_id=t.campaign_id,
                    occurred_at=t.occurred_at,
                )
                for t in touchpoints_db
            ]
            sync_results = run_all_sync_models(
                tp_list, datetime.now(timezone.utc)
            )
            for model_name, credits in sync_results.items():
                await attr_repo.save_results(
                    session, conversion_id, profile_id, model_name, credits, revenue
                )
            await session.commit()

        graph_payload = []
        async with AsyncSessionFactory() as session:
            results_db = await attr_repo.get_results_for_profile(
                session, profile_id, model="linear"
            )
        for r in results_db:
            graph_payload.append(
                {
                    "model": "linear",
                    "channel": r.channel,
                    "campaign_id": r.campaign_id,
                    "credit": r.credit,
                    "revenue_credit": r.revenue_credit,
                }
            )

        asyncio.create_task(
            sync_attribution_to_graph(
                str(profile_id),
                str(conversion_id),
                revenue,
                currency,
                graph_payload,
            )
        )
        await publish(
            SHAPLEY_SUBJECT,
            {
                "conversion_id": str(conversion_id),
                "profile_id": str(profile_id),
                "revenue": revenue,
            },
        )
    except Exception as e:
        logger.error("VTEX attribution failed: %s", e)


async def _save_vtex_order(
    session,
    vtex_order_id,
    account_name,
    profile_id,
    conversion_id,
    channel,
    total_price,
    currency,
    status,
    email=None,
    phone=None,
) -> None:
    await session.execute(
        sql_text("""
            INSERT INTO vtex_orders
                (id, vtex_order_id, account_name, profile_id, conversion_id,
                 email, phone, total_price, currency, channel, processing_status, raw_payload)
            VALUES
                (:id, :oid, :account, :profile_id, :conversion_id,
                 :email, :phone, :total, :currency, :channel, :status,
                 CAST(:raw AS jsonb))
            ON CONFLICT (vtex_order_id) DO NOTHING
        """),
        {
            "id": str(uuid.uuid4()),
            "oid": vtex_order_id,
            "account": account_name,
            "profile_id": str(profile_id) if profile_id else None,
            "conversion_id": str(conversion_id) if conversion_id else None,
            "email": email,
            "phone": phone,
            "total": float(total_price or 0),
            "currency": currency,
            "channel": channel,
            "status": status,
            "raw": json.dumps(
                {"vtex_order_id": vtex_order_id, "account": account_name}
            ),
        },
    )
