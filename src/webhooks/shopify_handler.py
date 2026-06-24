import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text as sql_text

from src.attribution import repository as attr_repo
from src.attribution.models_math import Touchpoint, run_all_sync_models
from src.database import AsyncSessionFactory
from src.graphs.revenue_graph import sync_attribution_to_graph
from src.identity.resolver import resolve as resolve_identity
from src.nats_client import publish
from src.webhooks.order_parser import (
    determine_channel,
    extract_line_items,
    extract_revenue,
    extract_signals,
    extract_utms,
)

logger = logging.getLogger(__name__)
SHAPLEY_SUBJECT = "attribution.shapley.compute"


async def process_shopify_order(order: dict) -> None:
    """
    Pipeline completo para uma ordem Shopify.
    Chamado como asyncio.create_task — não bloqueia o endpoint.

    Idempotente: usa shopify_order_id como chave única.
    """
    try:
        await _process_shopify_order_inner(order)
    except Exception:
        logger.exception("Failed to process Shopify order %s", order.get("id"))


async def _process_shopify_order_inner(order: dict) -> None:
    shopify_order_id = str(order.get("id", ""))
    if not shopify_order_id:
        logger.error("Ordem sem ID — ignorando")
        return

    logger.info("Processing Shopify order %s", shopify_order_id)

    profile_id: UUID | None = None
    conversion_id: UUID | None = None
    revenue = 0.0
    currency = "BRL"

    async with AsyncSessionFactory() as session:
        existing = await session.execute(
            sql_text("SELECT id FROM shopify_orders WHERE shopify_order_id = :oid"),
            {"oid": shopify_order_id},
        )
        if existing.fetchone():
            logger.info("Order %s already processed — skipping", shopify_order_id)
            return

        signals = extract_signals(order)
        if not signals:
            logger.warning(
                "Order %s has no identity signals (no email/phone)",
                shopify_order_id,
            )
            await _save_order_record(session, order, shopify_order_id, None, None)
            await session.commit()
            return

        utms = extract_utms(order)
        channel = determine_channel(utms)
        revenue, currency = extract_revenue(order)

        identity_result = await resolve_identity(session, signals, source="shopify")
        profile_id = UUID(identity_result["profile_id"])
        logger.info(
            "Order %s → profile %s (signals: %s)",
            shopify_order_id,
            profile_id,
            identity_result["signals_count"],
        )

        has_tracking = any([
            utms.get("utm_source"),
            utms.get("gclid"),
            utms.get("fbclid"),
        ])
        if has_tracking:
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
                metadata={"shopify_order_id": shopify_order_id},
            )

        conversion = await attr_repo.create_conversion(
            session,
            profile_id=profile_id,
            revenue=revenue,
            currency=currency,
            metadata={
                "shopify_order_id": shopify_order_id,
                "channel": channel,
                "line_items_count": len(order.get("line_items", [])),
            },
        )
        conversion_id = conversion.id

        await _save_order_record(
            session,
            order,
            shopify_order_id,
            profile_id,
            conversion_id,
            channel=channel,
            utms=utms,
        )
        await session.commit()

    if profile_id and conversion_id:
        from src.integrations.meta_capi import send_purchase_event

        asyncio.create_task(
            send_purchase_event(
                shopify_order_id=shopify_order_id,
                email=order.get("email"),
                phone=order.get("phone") or order.get("billing_address", {}).get("phone"),
                revenue=revenue,
                currency=currency,
                event_source_url=order.get("order_status_url"),
            )
        )
        asyncio.create_task(
            _compute_attribution(profile_id, conversion_id, revenue, currency)
        )
        logger.info(
            "Order %s processed OK — profile=%s, revenue=%s %s",
            shopify_order_id,
            profile_id,
            revenue,
            currency,
        )


async def _compute_attribution(
    profile_id: UUID,
    conversion_id: UUID,
    revenue: float,
    currency: str,
) -> None:
    """Computa modelos de atribuição e sincroniza ao grafo. Fire-and-forget."""
    try:
        async with AsyncSessionFactory() as session:
            touchpoints_db = await attr_repo.get_touchpoints_for_profile(session, profile_id)
            conversion_time = datetime.now(timezone.utc)

            if not touchpoints_db:
                logger.info("No touchpoints for %s — zero-touch conversion", profile_id)
                return

            tp_list = [
                Touchpoint(
                    channel=t.channel,
                    campaign_id=t.campaign_id,
                    occurred_at=t.occurred_at,
                )
                for t in touchpoints_db
            ]
            sync_results = run_all_sync_models(tp_list, conversion_time)

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
            graph_payload.append({
                "model": "linear",
                "channel": r.channel,
                "campaign_id": r.campaign_id,
                "credit": r.credit,
                "revenue_credit": r.revenue_credit,
            })

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
        logger.error(
            "Attribution compute failed for conversion %s: %s",
            conversion_id,
            e,
        )


async def _save_order_record(
    session,
    order: dict,
    shopify_order_id: str,
    profile_id,
    conversion_id,
    channel: str | None = None,
    utms: dict | None = None,
) -> None:
    utms = utms or {}
    await session.execute(
        sql_text("""
            INSERT INTO shopify_orders
                (id, shopify_order_id, profile_id, conversion_id,
                 email, phone, total_price, currency,
                 utm_source, utm_medium, utm_campaign, gclid, fbclid,
                 channel, referring_site, line_items, raw_payload, processing_status)
            VALUES
                (:id, :shopify_order_id, :profile_id, :conversion_id,
                 :email, :phone, :total_price, :currency,
                 :utm_source, :utm_medium, :utm_campaign, :gclid, :fbclid,
                 :channel, :referring_site,
                 CAST(:line_items AS jsonb), CAST(:raw_payload AS jsonb),
                 'done')
            ON CONFLICT (shopify_order_id) DO NOTHING
        """),
        {
            "id": str(uuid.uuid4()),
            "shopify_order_id": shopify_order_id,
            "profile_id": str(profile_id) if profile_id else None,
            "conversion_id": str(conversion_id) if conversion_id else None,
            "email": order.get("email"),
            "phone": order.get("phone") or order.get("billing_address", {}).get("phone"),
            "total_price": float(order.get("total_price") or "0"),
            "currency": order.get("currency", "BRL"),
            "utm_source": utms.get("utm_source"),
            "utm_medium": utms.get("utm_medium"),
            "utm_campaign": utms.get("utm_campaign"),
            "gclid": utms.get("gclid"),
            "fbclid": utms.get("fbclid"),
            "channel": channel,
            "referring_site": utms.get("referring_site"),
            "line_items": json.dumps(extract_line_items(order)),
            "raw_payload": json.dumps({
                "id": order.get("id"),
                "order_number": order.get("order_number"),
                "financial_status": order.get("financial_status"),
            }),
        },
    )
