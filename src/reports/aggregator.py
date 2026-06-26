"""
Agrega métricas semanais por loja a partir das 8 tabelas de ordens.
Compara semana atual vs semana anterior.
Não faz nenhuma escrita no banco — read-only.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import text as sql_text

from src.database import AsyncSessionFactory

PLATFORM_MAP = {
    "shopify": ("shopify_orders", "shop_domain"),
    "tray": ("tray_orders", "seller_id"),
    "nuvemshop": ("nuvemshop_orders", "store_id"),
    "vtex": ("vtex_orders", "account_name"),
    "woocommerce": ("woocommerce_orders", "store_url"),
    "loja_integrada": ("loja_integrada_orders", "store_key"),
    "moovin": ("moovin_orders", "store_id"),
    "generic": ("generic_orders", "store_id"),
}


def get_week_range(weeks_back: int = 1) -> tuple[datetime, datetime]:
    """
    Retorna (start, end) da semana solicitada.
    weeks_back=1 → semana passada (seg 00:00 a dom 23:59)
    weeks_back=0 → semana atual até agora
    """
    now = datetime.now(timezone.utc)
    days_since_monday = now.weekday()
    current_monday = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start = current_monday - timedelta(weeks=weeks_back)
    end = (current_monday - timedelta(seconds=1)) if weeks_back > 0 else now
    return start, end


async def get_weekly_metrics(
    platform: str,
    store_identifier: str,
    weeks_back: int = 1,
) -> dict | None:
    if platform not in PLATFORM_MAP:
        return None

    table, col = PLATFORM_MAP[platform]
    start, end = get_week_range(weeks_back)
    p_start, p_end = get_week_range(weeks_back + 1)

    async with AsyncSessionFactory() as session:
        current = await session.execute(
            sql_text(f"""
                SELECT
                    COUNT(*)                        AS order_count,
                    COALESCE(SUM(total_price), 0)  AS total_revenue,
                    COALESCE(AVG(total_price), 0)  AS avg_order_value,
                    COUNT(DISTINCT profile_id)      AS unique_customers
                FROM {table}
                WHERE {col} = :sid
                  AND processing_status = 'done'
                  AND created_at BETWEEN :start AND :end
            """),
            {"sid": store_identifier, "start": start, "end": end},
        )
        cur = current.fetchone()

        previous = await session.execute(
            sql_text(f"""
                SELECT COALESCE(SUM(total_price), 0) AS total_revenue
                FROM {table}
                WHERE {col} = :sid
                  AND processing_status = 'done'
                  AND created_at BETWEEN :start AND :end
            """),
            {"sid": store_identifier, "start": p_start, "end": p_end},
        )
        prev = previous.fetchone()

        channels = await session.execute(
            sql_text(f"""
                SELECT
                    COALESCE(channel, 'direto')  AS channel,
                    COUNT(*)                     AS order_count,
                    SUM(total_price)             AS revenue
                FROM {table}
                WHERE {col} = :sid
                  AND processing_status = 'done'
                  AND created_at BETWEEN :start AND :end
                GROUP BY channel
                ORDER BY revenue DESC
                LIMIT 3
            """),
            {"sid": store_identifier, "start": start, "end": end},
        )
        top_channels = [dict(r._mapping) for r in channels.fetchall()]

        campaign = await session.execute(
            sql_text(f"""
                SELECT utm_campaign, SUM(total_price) AS revenue
                FROM {table}
                WHERE {col} = :sid
                  AND processing_status = 'done'
                  AND utm_campaign IS NOT NULL
                  AND created_at BETWEEN :start AND :end
                GROUP BY utm_campaign
                ORDER BY revenue DESC
                LIMIT 1
            """),
            {"sid": store_identifier, "start": start, "end": end},
        )
        top_campaign_row = campaign.fetchone()

    if cur is None:
        return None

    current_revenue = float(cur.total_revenue)
    previous_revenue = float(prev.total_revenue) if prev else 0.0

    revenue_change_pct = None
    if previous_revenue > 0:
        revenue_change_pct = round(
            ((current_revenue - previous_revenue) / previous_revenue) * 100, 1
        )

    return {
        "period": {
            "start": start.strftime("%d/%m/%Y"),
            "end": end.strftime("%d/%m/%Y"),
        },
        "current_week": {
            "order_count": int(cur.order_count),
            "total_revenue": current_revenue,
            "avg_order_value": round(float(cur.avg_order_value), 2),
            "unique_customers": int(cur.unique_customers),
        },
        "previous_week": {
            "total_revenue": previous_revenue,
        },
        "revenue_change_pct": revenue_change_pct,
        "top_channels": [
            {
                "channel": r["channel"],
                "order_count": int(r["order_count"]),
                "revenue": float(r["revenue"]),
            }
            for r in top_channels
        ],
        "top_campaign": top_campaign_row.utm_campaign if top_campaign_row else None,
        "platform": platform,
        "store_identifier": store_identifier,
    }


async def get_all_active_stores_metrics(weeks_back: int = 1) -> list[dict]:
    """
    Retorna métricas de todas as lojas que tiveram atividade na semana.
    Itera por todas as plataformas.
    """
    start, end = get_week_range(weeks_back)
    results: list[dict] = []

    for platform, (table, col) in PLATFORM_MAP.items():
        async with AsyncSessionFactory() as session:
            rows = await session.execute(
                sql_text(f"""
                    SELECT DISTINCT {col} AS store_id
                    FROM {table}
                    WHERE processing_status = 'done'
                      AND created_at BETWEEN :start AND :end
                """),
                {"start": start, "end": end},
            )
            store_ids = [r.store_id for r in rows.fetchall()]

        for store_id in store_ids:
            metrics = await get_weekly_metrics(platform, store_id, weeks_back)
            if metrics and metrics["current_week"]["order_count"] > 0:
                results.append(metrics)

    return results
