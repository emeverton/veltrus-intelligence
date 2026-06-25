"""
Handler genérico — recebe payload já normalizado pelo n8n/Make/Zapier.
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
from src.webhooks.tray_handler import check_usage_limit
from src.webhooks.woocommerce_parser import determine_channel

logger = logging.getLogger(__name__)
SHAPLEY_SUBJECT = "attribution.shapley.compute"


async def process_generic_order(payload: dict, store: dict) -> None:
    try:
        await _process_generic_order_inner(payload, store)
    except Exception:
        logger.exception(
            "Failed to process generic order %s",
            payload.get("order_id"),
        )


async def _process_generic_order_inner(payload: dict, store: dict) -> None:
    store_id = payload.get("store_id") or store["store_id"]
    order_id = str(payload.get("order_id", ""))
    platform = payload.get("platform", store.get("platform", "other"))

    if not order_id:
        logger.error("Generic order sem order_id")
        return

    async with AsyncSessionFactory() as session:
        existing = await session.execute(
            sql_text(
                """
                SELECT id FROM generic_orders
                WHERE store_id = :sid AND order_id = :oid
                """
            ),
            {"sid": store_id, "oid": order_id},
        )
        if existing.fetchone():
            logger.info("Generic order %s (%s) already processed", order_id, platform)
            return

        within_limit, count = await check_usage_limit(store_id, "generic")
        if not within_limit:
            logger.warning("Generic store %s exceeded limit (%s)", store_id, count)
            await _save_generic_order(
                session,
                order_id,
                store_id,
                platform,
                None,
                None,
                None,
                0,
                "BRL",
                "limit_exceeded",
            )
            await session.commit()
            return

        signals = []
        email = payload.get("email")
        if email and "@" in email:
            signals.append({"type": "email", "value": email.strip().lower()})
        if payload.get("phone"):
            signals.append({"type": "phone", "value": payload["phone"]})

        if not signals:
            await _save_generic_order(
                session,
                order_id,
                store_id,
                platform,
                None,
                None,
                None,
                float(payload.get("revenue", 0)),
                payload.get("currency", "BRL"),
                "no_signals",
            )
            await session.commit()
            return

        utms = {
            "utm_source": payload.get("utm_source"),
            "utm_medium": payload.get("utm_medium"),
            "utm_campaign": payload.get("utm_campaign"),
            "gclid": payload.get("gclid"),
            "fbclid": payload.get("fbclid"),
        }
        channel = determine_channel(utms)
        revenue = float(payload.get("revenue", 0))
        currency = payload.get("currency", "BRL").upper()

        identity_result = await resolve_identity(session, signals, source=platform)
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
                metadata={"order_id": order_id, "platform": platform},
            )

        conversion = await attr_repo.create_conversion(
            session,
            profile_id=profile_id,
            revenue=revenue,
            currency=currency,
            metadata={
                "order_id": order_id,
                "platform": platform,
                "channel": channel,
            },
        )

        await _save_generic_order(
            session,
            order_id,
            store_id,
            platform,
            profile_id,
            conversion.id,
            channel,
            revenue,
            currency,
            "done",
            email=payload.get("email"),
            phone=payload.get("phone"),
            utms=utms,
        )
        await session.commit()

    asyncio.create_task(
        _compute_attribution(profile_id, conversion.id, revenue, currency)
    )

    if store.get("meta_pixel_id") and store.get("meta_access_token"):
        from src.integrations.meta_capi import send_purchase_event

        asyncio.create_task(
            send_purchase_event(
                shopify_order_id=f"{platform}_{order_id}",
                email=payload.get("email"),
                phone=payload.get("phone"),
                revenue=revenue,
                currency=currency,
                pixel_id_override=store.get("meta_pixel_id"),
                access_token_override=store.get("meta_access_token"),
                test_event_code_override=store.get("meta_test_event_code"),
            )
        )


async def _save_generic_order(
    session,
    order_id,
    store_id,
    platform,
    profile_id,
    conversion_id,
    channel,
    total,
    currency,
    status,
    email=None,
    phone=None,
    utms=None,
) -> None:
    utms = utms or {}
    await session.execute(
        sql_text("""
            INSERT INTO generic_orders
                (id, order_id, store_id, platform, profile_id, conversion_id,
                 email, phone, total_price, currency, utm_source, utm_medium,
                 utm_campaign, channel, processing_status, raw_payload)
            VALUES (:id, :oid, :sid, :platform, :pid, :cid,
                    :email, :phone, :total, :currency, :src, :med,
                    :campaign, :channel, :status,
                    CAST(:raw AS jsonb))
            ON CONFLICT ON CONSTRAINT uq_generic_order DO NOTHING
        """),
        {
            "id": str(uuid.uuid4()),
            "oid": order_id,
            "sid": store_id,
            "platform": platform,
            "pid": str(profile_id) if profile_id else None,
            "cid": str(conversion_id) if conversion_id else None,
            "email": email,
            "phone": phone,
            "total": float(total or 0),
            "currency": currency,
            "src": utms.get("utm_source"),
            "med": utms.get("utm_medium"),
            "campaign": utms.get("utm_campaign"),
            "channel": channel,
            "status": status,
            "raw": json.dumps(
                {
                    "order_id": order_id,
                    "store_id": store_id,
                    "platform": platform,
                }
            ),
        },
    )


async def _compute_attribution(profile_id, conversion_id, revenue, currency) -> None:
    try:
        async with AsyncSessionFactory() as session:
            tps = await attr_repo.get_touchpoints_for_profile(session, profile_id)
            if not tps:
                return
            tp_list = [
                Touchpoint(
                    channel=t.channel,
                    campaign_id=t.campaign_id,
                    occurred_at=t.occurred_at,
                )
                for t in tps
            ]
            results = run_all_sync_models(tp_list, datetime.now(timezone.utc))
            for model, credits in results.items():
                await attr_repo.save_results(
                    session, conversion_id, profile_id, model, credits, revenue
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
        logger.error("Generic attribution failed: %s", e)
