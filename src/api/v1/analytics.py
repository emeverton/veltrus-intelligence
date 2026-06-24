"""
Endpoint de analytics agregado — primeiro valor visível para o usuário.
"""
from fastapi import APIRouter
from sqlalchemy import text as sql_text

from src.database import AsyncSessionFactory

router = APIRouter()


@router.get("/summary")
async def analytics_summary():
    """
    Resumo executivo do pipeline de dados.
    Retorna: profiles, conversões, receita por canal (últimos 30 dias), top LTV.
    """
    async with AsyncSessionFactory() as session:
        profiles = await session.execute(
            sql_text("SELECT COUNT(*) FROM identity_profiles")
        )
        total_profiles = profiles.scalar()

        conversions = await session.execute(
            sql_text("""
                SELECT COUNT(*) AS total,
                       COALESCE(SUM(revenue), 0) AS total_revenue,
                       currency
                FROM attribution_conversions
                WHERE occurred_at >= NOW() - INTERVAL '30 days'
                GROUP BY currency
                ORDER BY total_revenue DESC
                LIMIT 1
            """)
        )
        conv_row = conversions.fetchone()

        by_channel = await session.execute(
            sql_text("""
                SELECT ar.channel,
                       COUNT(DISTINCT ar.conversion_id) AS conversions,
                       ROUND(SUM(ar.revenue_credit)::numeric, 2) AS revenue_credit
                FROM attribution_results ar
                JOIN attribution_conversions ac ON ac.id = ar.conversion_id
                WHERE ar.model = 'linear'
                  AND ac.occurred_at >= NOW() - INTERVAL '30 days'
                GROUP BY ar.channel
                ORDER BY revenue_credit DESC
                LIMIT 10
            """)
        )
        channels = by_channel.fetchall()

        top_ltv = await session.execute(
            sql_text("""
                SELECT profile_id,
                       COUNT(*) AS conversions,
                       ROUND(SUM(revenue)::numeric, 2) AS ltv
                FROM attribution_conversions
                GROUP BY profile_id
                ORDER BY ltv DESC
                LIMIT 5
            """)
        )
        ltv_rows = top_ltv.fetchall()

        shopify_count = await session.execute(
            sql_text(
                "SELECT COUNT(*) FROM shopify_orders "
                "WHERE created_at >= NOW() - INTERVAL '30 days'"
            )
        )

    return {
        "period": "last_30_days",
        "profiles": {
            "total": total_profiles,
        },
        "shopify_orders": shopify_count.scalar(),
        "conversions": {
            "total": conv_row.total if conv_row else 0,
            "total_revenue": float(conv_row.total_revenue) if conv_row else 0.0,
            "currency": conv_row.currency if conv_row else "BRL",
        },
        "revenue_by_channel": [
            {
                "channel": r.channel,
                "conversions": r.conversions,
                "revenue_credit": float(r.revenue_credit),
            }
            for r in channels
        ],
        "top_profiles_by_ltv": [
            {
                "profile_id": str(r.profile_id),
                "conversions": r.conversions,
                "ltv": float(r.ltv),
            }
            for r in ltv_rows
        ],
    }
