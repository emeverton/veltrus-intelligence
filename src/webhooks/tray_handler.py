"""
Handler de ordens Tray Commerce.
Reutiliza o mesmo pipeline identity → attribution → graph do Shopify.
"""
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
from src.webhooks.tray_parser import (
    determine_tray_channel,
    extract_tray_order_id,
    extract_tray_revenue,
    extract_tray_seller_id,
    extract_tray_signals,
    extract_tray_utms,
)

logger = logging.getLogger(__name__)
SHAPLEY_SUBJECT = "attribution.shapley.compute"
FREE_LIMIT = 100


async def check_usage_limit(
    seller_id: str, source: str = "tray"
) -> tuple[bool, int]:
    """
    Verifica se a loja atingiu o limite mensal de ordens.
    Retorna (dentro_do_limite, contagem_atual).
    """
    async with AsyncSessionFactory() as session:
        if source == "tray":
            result = await session.execute(
                sql_text("""
                    SELECT COUNT(*) FROM tray_orders
                    WHERE seller_id = :seller_id
                      AND created_at >= DATE_TRUNC('month', NOW())
                """),
                {"seller_id": seller_id},
            )
        else:
            result = await session.execute(
                sql_text("""
                    SELECT COUNT(*) FROM shopify_orders
                    WHERE shop_domain = :domain
                      AND created_at >= DATE_TRUNC('month', NOW())
                """),
                {"domain": seller_id},
            )
        count = result.scalar() or 0

    return count < FREE_LIMIT, count


async def process_tray_order(payload: dict, store: dict) -> None:
    """Pipeline completo para uma ordem Tray. Idempotente via tray_order_id UNIQUE."""
    try:
        await _process_tray_order_inner(payload, store)
    except Exception:
        logger.exception(
            "Failed to process Tray order %s",
            payload.get("order", {}).get("id"),
        )


async def _process_tray_order_inner(payload: dict, store: dict) -> None:
    tray_order_id = extract_tray_order_id(payload)
    seller_id = extract_tray_seller_id(payload)

    if not tray_order_id:
        logger.error("Ordem Tray sem ID — ignorando")
        return

    logger.info("Processing Tray order %s from seller %s", tray_order_id, seller_id)

    async with AsyncSessionFactory() as session:
        existing = await session.execute(
            sql_text("SELECT id FROM tray_orders WHERE tray_order_id = :oid"),
            {"oid": tray_order_id},
        )
        if existing.fetchone():
            logger.info("Tray order %s already processed", tray_order_id)
            return

        within_limit, current_count = await check_usage_limit(seller_id, "tray")
        if not within_limit:
            logger.warning(
                "Tray seller %s exceeded monthly limit (%s orders) — skipping attribution",
                seller_id,
                current_count,
            )
            await _save_tray_order(
                session,
                payload,
                tray_order_id,
                seller_id,
                None,
                None,
                None,
                "limit_exceeded",
            )
            await session.commit()
            return

        signals = extract_tray_signals(payload)
        if not signals:
            logger.warning("Tray order %s sem sinais de identidade", tray_order_id)
            await _save_tray_order(
                session,
                payload,
                tray_order_id,
                seller_id,
                None,
                None,
                None,
                "no_signals",
            )
            await session.commit()
            return

        utms = extract_tray_utms(payload)
        channel = determine_tray_channel(utms)
        revenue, currency = extract_tray_revenue(payload)

        identity_result = await resolve_identity(session, signals, source="tray")
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
                metadata={"tray_order_id": tray_order_id, "seller_id": seller_id},
            )

        conversion = await attr_repo.create_conversion(
            session,
            profile_id=profile_id,
            revenue=revenue,
            currency=currency,
            metadata={
                "tray_order_id": tray_order_id,
                "seller_id": seller_id,
                "channel": channel,
            },
        )

        await _save_tray_order(
            session,
            payload,
            tray_order_id,
            seller_id,
            profile_id,
            conversion.id,
            channel,
            "done",
        )
        await session.commit()

    asyncio.create_task(
        _compute_tray_attribution(profile_id, conversion.id, revenue, currency)
    )

    if store.get("meta_pixel_id") and store.get("meta_access_token"):
        from src.integrations.meta_capi import send_purchase_event

        order = payload.get("order", {})
        customer = order.get("customer", {})
        asyncio.create_task(
            send_purchase_event(
                shopify_order_id=f"tray_{tray_order_id}",
                email=customer.get("email"),
                phone=customer.get("phone"),
                revenue=revenue,
                currency=currency,
                pixel_id_override=store.get("meta_pixel_id"),
                access_token_override=store.get("meta_access_token"),
                test_event_code_override=store.get("meta_test_event_code"),
            )
        )


async def _compute_tray_attribution(
    profile_id: UUID,
    conversion_id: UUID,
    revenue: float,
    currency: str,
) -> None:
    """Calcula atribuição e sincroniza ao grafo."""
    try:
        async with AsyncSessionFactory() as session:
            touchpoints_db = await attr_repo.get_touchpoints_for_profile(
                session, profile_id
            )
            conversion_time = datetime.now(timezone.utc)

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
        logger.error("Tray attribution failed: %s", e)


async def _save_tray_order(
    session,
    payload,
    tray_order_id,
    seller_id,
    profile_id,
    conversion_id,
    channel,
    status,
) -> None:
    order = payload.get("order", {})
    customer = order.get("customer", {})
    await session.execute(
        sql_text("""
            INSERT INTO tray_orders
                (id, tray_order_id, seller_id, profile_id, conversion_id,
                 email, phone, total_price, currency, channel, processing_status, raw_payload)
            VALUES
                (:id, :tray_order_id, :seller_id, :profile_id, :conversion_id,
                 :email, :phone, :total_price, :currency, :channel, :status,
                 CAST(:raw_payload AS jsonb))
            ON CONFLICT (tray_order_id) DO NOTHING
        """),
        {
            "id": str(uuid.uuid4()),
            "tray_order_id": tray_order_id,
            "seller_id": seller_id,
            "profile_id": str(profile_id) if profile_id else None,
            "conversion_id": str(conversion_id) if conversion_id else None,
            "email": customer.get("email"),
            "phone": customer.get("phone"),
            "total_price": float(order.get("value") or "0"),
            "currency": "BRL",
            "channel": channel,
            "status": status,
            "raw_payload": json.dumps(
                {
                    "id": tray_order_id,
                    "seller_id": seller_id,
                    "status_id": order.get("status_id"),
                }
            ),
        },
    )
