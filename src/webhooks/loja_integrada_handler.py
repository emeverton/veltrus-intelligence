"""Handler Loja Integrada — pipeline completo."""
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
from src.webhooks.loja_integrada_parser import (
    extract_li_order_id,
    extract_li_revenue,
    extract_li_signals,
    extract_li_utms,
)
from src.webhooks.tray_handler import check_usage_limit
from src.webhooks.woocommerce_parser import determine_channel

logger = logging.getLogger(__name__)
SHAPLEY_SUBJECT = "attribution.shapley.compute"


async def process_li_order(payload: dict, store: dict) -> None:
    try:
        await _process_li_order_inner(payload, store)
    except Exception:
        logger.exception(
            "Failed to process LI order %s", extract_li_order_id(payload)
        )


async def _process_li_order_inner(payload: dict, store: dict) -> None:
    store_key = store["store_key"]
    order_id = extract_li_order_id(payload)

    if not order_id:
        return

    async with AsyncSessionFactory() as session:
        existing = await session.execute(
            sql_text(
                "SELECT id FROM loja_integrada_orders "
                "WHERE store_key=:sk AND li_order_id=:oid"
            ),
            {"sk": store_key, "oid": order_id},
        )
        if existing.fetchone():
            return

        within_limit, _ = await check_usage_limit(store_key, "loja_integrada")
        if not within_limit:
            await _save(
                session,
                order_id,
                store_key,
                None,
                None,
                None,
                0,
                "BRL",
                "limit_exceeded",
            )
            await session.commit()
            return

        signals = extract_li_signals(payload)
        utms = extract_li_utms(payload)
        channel = determine_channel(utms)
        revenue, currency = extract_li_revenue(payload)

        if not signals:
            await _save(
                session,
                order_id,
                store_key,
                None,
                None,
                channel,
                revenue,
                currency,
                "no_signals",
            )
            await session.commit()
            return

        identity_result = await resolve_identity(
            session, signals, source="loja_integrada"
        )
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
                metadata={"li_order_id": order_id, "store_key": store_key},
            )

        conversion = await attr_repo.create_conversion(
            session,
            profile_id=profile_id,
            revenue=revenue,
            currency=currency,
            metadata={
                "li_order_id": order_id,
                "store_key": store_key,
                "channel": channel,
            },
        )

        cliente = payload.get("cliente") or {}
        await _save(
            session,
            order_id,
            store_key,
            profile_id,
            conversion.id,
            channel,
            revenue,
            currency,
            "done",
            email=cliente.get("email"),
            phone=str(cliente.get("fone", "") or ""),
            utms=utms,
        )
        await session.commit()

    asyncio.create_task(
        _compute_attribution(profile_id, conversion.id, revenue, currency)
    )

    if store.get("meta_pixel_id") and store.get("meta_access_token"):
        from src.integrations.meta_capi import send_purchase_event

        cliente = payload.get("cliente") or {}
        asyncio.create_task(
            send_purchase_event(
                shopify_order_id=f"li_{order_id}",
                email=cliente.get("email"),
                phone=str(cliente.get("fone", "") or ""),
                revenue=revenue,
                currency=currency,
                pixel_id_override=store.get("meta_pixel_id"),
                access_token_override=store.get("meta_access_token"),
                test_event_code_override=store.get("meta_test_event_code"),
            )
        )


async def _save(
    session,
    order_id,
    store_key,
    profile_id,
    conversion_id,
    channel,
    total,
    currency,
    status,
    email=None,
    phone=None,
    utms=None,
):
    utms = utms or {}
    await session.execute(
        sql_text("""
            INSERT INTO loja_integrada_orders
                (id, li_order_id, store_key, profile_id, conversion_id,
                 email, phone, total_price, currency, utm_source, utm_medium,
                 utm_campaign, channel, processing_status, raw_payload)
            VALUES (:id, :oid, :sk, :pid, :cid,
                    :email, :phone, :total, :currency, :src, :med,
                    :campaign, :channel, :status, :raw::jsonb)
            ON CONFLICT ON CONSTRAINT uq_li_order DO NOTHING
        """),
        {
            "id": str(uuid.uuid4()),
            "oid": order_id,
            "sk": store_key,
            "pid": str(profile_id) if profile_id else None,
            "cid": str(conversion_id) if conversion_id else None,
            "email": email,
            "phone": phone or None,
            "total": float(total or 0),
            "currency": currency,
            "src": utms.get("utm_source"),
            "med": utms.get("utm_medium"),
            "campaign": utms.get("utm_campaign"),
            "channel": channel,
            "status": status,
            "raw": json.dumps({"li_order_id": order_id, "store_key": store_key}),
        },
    )


async def _compute_attribution(profile_id, conversion_id, revenue, currency):
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
        async with AsyncSessionFactory() as session:
            results_db = await attr_repo.get_results_for_profile(
                session, profile_id, model="linear"
            )
        graph_payload = [
            {
                "model": "linear",
                "channel": r.channel,
                "campaign_id": r.campaign_id,
                "credit": r.credit,
                "revenue_credit": r.revenue_credit,
            }
            for r in results_db
        ]
        asyncio.create_task(
            sync_attribution_to_graph(
                str(profile_id), str(conversion_id), revenue, currency, graph_payload
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
        logger.error("LI attribution failed: %s", e)
