"""
Handler de ordens Nuvemshop.
Reutiliza o mesmo pipeline identity → attribution → graph.
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
from src.webhooks.nuvemshop_parser import (
    determine_nuvemshop_channel,
    extract_nuvemshop_order_id,
    extract_nuvemshop_revenue,
    extract_nuvemshop_signals,
    extract_nuvemshop_store_id,
    extract_nuvemshop_utms,
)
from src.webhooks.tray_handler import check_usage_limit

logger = logging.getLogger(__name__)
SHAPLEY_SUBJECT = "attribution.shapley.compute"


async def process_nuvemshop_order(payload: dict, store: dict) -> None:
    try:
        await _process_nuvemshop_order_inner(payload, store)
    except Exception:
        logger.exception(
            "Failed to process Nuvemshop order %s", payload.get("id")
        )


async def _process_nuvemshop_order_inner(payload: dict, store: dict) -> None:
    order_id = extract_nuvemshop_order_id(payload)
    store_id = extract_nuvemshop_store_id(payload)

    if not order_id:
        logger.error("Ordem Nuvemshop sem ID — ignorando")
        return

    logger.info("Processing Nuvemshop order %s from store %s", order_id, store_id)

    async with AsyncSessionFactory() as session:
        existing = await session.execute(
            sql_text("SELECT id FROM nuvemshop_orders WHERE nuvemshop_order_id = :oid"),
            {"oid": order_id},
        )
        if existing.fetchone():
            logger.info("Nuvemshop order %s already processed", order_id)
            return

        within_limit, current_count = await check_usage_limit(store_id, "nuvemshop")
        if not within_limit:
            logger.warning(
                "Nuvemshop store %s exceeded limit (%s) — skipping attribution",
                store_id,
                current_count,
            )
            await _save_nuvemshop_order(
                session, payload, order_id, store_id, None, None, None, "limit_exceeded"
            )
            await session.commit()
            return

        signals = extract_nuvemshop_signals(payload)
        if not signals:
            logger.warning("Nuvemshop order %s sem sinais de identidade", order_id)
            await _save_nuvemshop_order(
                session, payload, order_id, store_id, None, None, None, "no_signals"
            )
            await session.commit()
            return

        utms = extract_nuvemshop_utms(payload)
        channel = determine_nuvemshop_channel(utms)
        revenue, currency = extract_nuvemshop_revenue(payload)

        identity_result = await resolve_identity(session, signals, source="nuvemshop")
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
                metadata={"nuvemshop_order_id": order_id, "store_id": store_id},
            )

        conversion = await attr_repo.create_conversion(
            session,
            profile_id=profile_id,
            revenue=revenue,
            currency=currency,
            metadata={
                "nuvemshop_order_id": order_id,
                "store_id": store_id,
                "channel": channel,
            },
        )

        await _save_nuvemshop_order(
            session, payload, order_id, store_id, profile_id, conversion.id, channel, "done"
        )
        await session.commit()

    asyncio.create_task(
        _compute_nuvemshop_attribution(profile_id, conversion.id, revenue, currency)
    )

    if store.get("meta_pixel_id") and store.get("meta_access_token"):
        from src.integrations.meta_capi import send_purchase_event

        asyncio.create_task(
            send_purchase_event(
                shopify_order_id=f"nuvemshop_{order_id}",
                email=payload.get("contact_email"),
                phone=payload.get("contact_phone"),
                revenue=revenue,
                currency=currency,
                pixel_id_override=store.get("meta_pixel_id"),
                access_token_override=store.get("meta_access_token"),
                test_event_code_override=store.get("meta_test_event_code"),
            )
        )


async def _compute_nuvemshop_attribution(
    profile_id: UUID, conversion_id: UUID, revenue: float, currency: str
) -> None:
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
        logger.error("Nuvemshop attribution failed: %s", e)


async def _save_nuvemshop_order(
    session, payload, order_id, store_id, profile_id, conversion_id, channel, status
) -> None:
    await session.execute(
        sql_text("""
            INSERT INTO nuvemshop_orders
                (id, nuvemshop_order_id, store_id, profile_id, conversion_id,
                 email, phone, total_price, currency, channel, processing_status, raw_payload)
            VALUES
                (:id, :order_id, :store_id, :profile_id, :conversion_id,
                 :email, :phone, :total_price, :currency, :channel, :status,
                 CAST(:raw_payload AS jsonb))
            ON CONFLICT (nuvemshop_order_id) DO NOTHING
        """),
        {
            "id": str(uuid.uuid4()),
            "order_id": order_id,
            "store_id": store_id,
            "profile_id": str(profile_id) if profile_id else None,
            "conversion_id": str(conversion_id) if conversion_id else None,
            "email": payload.get("contact_email"),
            "phone": payload.get("contact_phone"),
            "total_price": float(payload.get("total") or "0"),
            "currency": (payload.get("currency") or "BRL").upper(),
            "channel": channel,
            "status": status,
            "raw_payload": json.dumps(
                {
                    "id": order_id,
                    "store_id": store_id,
                    "status": payload.get("status"),
                    "total": payload.get("total"),
                }
            ),
        },
    )
