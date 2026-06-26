"""
Motor de guardrails do KAIROS.
Filtra perfis que não devem receber outreach.
Todas as regras são automáticas — sem aprovação humana.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text as sql_text

from src.database import AsyncSessionFactory

COOLDOWN_DAYS = 7
MAX_ACTIVE_SEQUENCES = 1
HOUR_START_BRT = 8
HOUR_END_BRT = 21
BLOCKED_WEEKDAYS = {6}
COLD_LEAD_MIN_SIGNALS = 2
EXISTING_MIN_ORDER_VALUE = 50.0

ORDER_UNION = """
    SELECT profile_id, created_at, total_price, email, phone FROM shopify_orders
      WHERE processing_status = 'done' AND profile_id IS NOT NULL
    UNION ALL
    SELECT profile_id, created_at, total_price, email, phone FROM tray_orders
      WHERE processing_status = 'done' AND profile_id IS NOT NULL
    UNION ALL
    SELECT profile_id, created_at, total_price, email, phone FROM nuvemshop_orders
      WHERE processing_status = 'done' AND profile_id IS NOT NULL
    UNION ALL
    SELECT profile_id, created_at, total_price, email, phone FROM vtex_orders
      WHERE processing_status = 'done' AND profile_id IS NOT NULL
    UNION ALL
    SELECT profile_id, created_at, total_price, email, phone FROM woocommerce_orders
      WHERE processing_status = 'done' AND profile_id IS NOT NULL
    UNION ALL
    SELECT profile_id, created_at, total_price, email, phone FROM loja_integrada_orders
      WHERE processing_status = 'done' AND profile_id IS NOT NULL
    UNION ALL
    SELECT profile_id, created_at, total_price, email, phone FROM moovin_orders
      WHERE processing_status = 'done' AND profile_id IS NOT NULL
    UNION ALL
    SELECT profile_id, created_at, total_price, email, phone FROM generic_orders
      WHERE processing_status = 'done' AND profile_id IS NOT NULL
"""

CONTACT_EMAIL_SUBQUERY = f"""
    COALESCE(
        (SELECT email FROM ({ORDER_UNION}) oc
         WHERE oc.profile_id = ip.id AND oc.email IS NOT NULL
         ORDER BY oc.created_at DESC LIMIT 1),
        (SELECT event_data->>'email' FROM identity_events ie
         WHERE ie.profile_id = ip.id AND event_data->>'email' IS NOT NULL
         ORDER BY ie.occurred_at DESC LIMIT 1)
    )
"""

CONTACT_PHONE_SUBQUERY = f"""
    COALESCE(
        (SELECT phone FROM ({ORDER_UNION}) oc
         WHERE oc.profile_id = ip.id AND oc.phone IS NOT NULL
         ORDER BY oc.created_at DESC LIMIT 1),
        (SELECT event_data->>'phone' FROM identity_events ie
         WHERE ie.profile_id = ip.id AND event_data->>'phone' IS NOT NULL
         ORDER BY ie.occurred_at DESC LIMIT 1)
    )
"""

ALL_BUYERS_SUBQUERY = f"""
    SELECT DISTINCT profile_id FROM ({ORDER_UNION}) buyers
"""


def is_within_sending_window() -> tuple[bool, str]:
    """Verifica se está dentro da janela de envio (8h-21h BRT, seg-sáb)."""
    now_utc = datetime.now(timezone.utc)
    now_brt = now_utc - timedelta(hours=3)
    if now_brt.weekday() in BLOCKED_WEEKDAYS:
        return False, f"domingo bloqueado (weekday={now_brt.weekday()})"
    if not (HOUR_START_BRT <= now_brt.hour < HOUR_END_BRT):
        return False, f"fora da janela de envio ({now_brt.hour}h BRT)"
    return True, "ok"


async def check_profile_eligible(
    profile_id: str | UUID,
    segment: str,
) -> tuple[bool, str]:
    """Retorna (is_eligible, reason)."""
    profile_id_str = str(profile_id)
    async with AsyncSessionFactory() as session:
        opt_out = await session.execute(
            sql_text("SELECT id FROM kairos_opt_outs WHERE profile_id = :pid"),
            {"pid": profile_id_str},
        )
        if opt_out.fetchone():
            return False, "opt-out"

        active = await session.execute(
            sql_text("""
                SELECT COUNT(*) FROM kairos_sequences
                WHERE profile_id = :pid
                  AND status NOT IN ('completed', 'failed', 'opted_out')
            """),
            {"pid": profile_id_str},
        )
        if (active.scalar() or 0) >= MAX_ACTIVE_SEQUENCES:
            return False, "sequência ativa em andamento"

        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)
        last_completed = await session.execute(
            sql_text("""
                SELECT completed_at FROM kairos_sequences
                WHERE profile_id = :pid AND status = 'completed'
                ORDER BY completed_at DESC LIMIT 1
            """),
            {"pid": profile_id_str},
        )
        row = last_completed.fetchone()
        if row and row.completed_at and row.completed_at > cooldown_cutoff:
            return False, f"cooldown ativo (última sequência {row.completed_at.date()})"

        if segment == "cold_lead":
            signals = await session.execute(
                sql_text("""
                    SELECT COUNT(*) FROM identity_signals
                    WHERE profile_id = :pid
                      AND signal_type IN ('email', 'phone', 'gclid', 'fbclid', 'pixel_id')
                """),
                {"pid": profile_id_str},
            )
            if (signals.scalar() or 0) < COLD_LEAD_MIN_SIGNALS:
                return False, "cold lead com sinais insuficientes"

        contact = await session.execute(
            sql_text(f"""
                SELECT
                    COALESCE(
                        (SELECT email FROM ({ORDER_UNION}) oc
                         WHERE oc.profile_id = :pid::uuid AND oc.email IS NOT NULL
                         ORDER BY oc.created_at DESC LIMIT 1),
                        (SELECT event_data->>'email' FROM identity_events ie
                         WHERE ie.profile_id = :pid::uuid AND event_data->>'email' IS NOT NULL
                         ORDER BY ie.occurred_at DESC LIMIT 1)
                    ) AS email,
                    COALESCE(
                        (SELECT phone FROM ({ORDER_UNION}) oc
                         WHERE oc.profile_id = :pid::uuid AND oc.phone IS NOT NULL
                         ORDER BY oc.created_at DESC LIMIT 1),
                        (SELECT event_data->>'phone' FROM identity_events ie
                         WHERE ie.profile_id = :pid::uuid AND event_data->>'phone' IS NOT NULL
                         ORDER BY ie.occurred_at DESC LIMIT 1)
                    ) AS phone
            """),
            {"pid": profile_id_str},
        )
        contact_row = contact.fetchone()
        if not contact_row or (not contact_row.email and not contact_row.phone):
            return False, "sem email ou telefone para contato"

    return True, "elegível"


async def get_eligible_targets(
    segment: str,
    max_profiles: int = 50,
) -> list[dict]:
    """Retorna perfis elegíveis para outreach por segmento."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
    async with AsyncSessionFactory() as session:
        if segment == "existing_customer":
            result = await session.execute(
                sql_text(f"""
                    WITH profile_orders AS (
                        SELECT profile_id, MAX(created_at) AS last_order,
                               SUM(total_price) AS total_ltv,
                               COUNT(*) AS order_count
                        FROM ({ORDER_UNION}) all_orders
                        GROUP BY profile_id
                    )
                    SELECT
                        ip.id AS profile_id,
                        po.last_order,
                        po.total_ltv,
                        po.order_count,
                        {CONTACT_EMAIL_SUBQUERY} AS email,
                        {CONTACT_PHONE_SUBQUERY} AS phone
                    FROM identity_profiles ip
                    JOIN profile_orders po ON po.profile_id = ip.id
                    WHERE po.last_order < :cutoff
                      AND po.total_ltv >= :min_ltv
                      AND ip.id NOT IN (
                          SELECT profile_id FROM kairos_sequences
                          WHERE status NOT IN ('completed', 'failed', 'opted_out')
                      )
                      AND ip.id NOT IN (
                          SELECT profile_id FROM kairos_opt_outs WHERE profile_id IS NOT NULL
                      )
                    ORDER BY po.total_ltv DESC
                    LIMIT :limit
                """),
                {
                    "cutoff": cutoff_date,
                    "min_ltv": EXISTING_MIN_ORDER_VALUE,
                    "limit": max_profiles,
                },
            )
        else:
            result = await session.execute(
                sql_text(f"""
                    SELECT
                        ip.id AS profile_id,
                        NULL AS last_order,
                        0 AS total_ltv,
                        0 AS order_count,
                        {CONTACT_EMAIL_SUBQUERY} AS email,
                        {CONTACT_PHONE_SUBQUERY} AS phone
                    FROM identity_profiles ip
                    WHERE ip.id NOT IN ({ALL_BUYERS_SUBQUERY})
                      AND ip.id NOT IN (
                          SELECT profile_id FROM kairos_sequences
                          WHERE status NOT IN ('completed', 'failed', 'opted_out')
                      )
                      AND ip.id NOT IN (
                          SELECT profile_id FROM kairos_opt_outs WHERE profile_id IS NOT NULL
                      )
                      AND (
                          SELECT COUNT(*) FROM identity_signals
                          WHERE profile_id = ip.id
                            AND signal_type IN (
                                'email', 'phone', 'gclid', 'fbclid', 'pixel_id'
                            )
                      ) >= :min_signals
                    ORDER BY ip.created_at DESC
                    LIMIT :limit
                """),
                {"min_signals": COLD_LEAD_MIN_SIGNALS, "limit": max_profiles},
            )
        rows = result.fetchall()
        return [dict(r._mapping) for r in rows]
