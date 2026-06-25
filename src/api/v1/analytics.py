"""
Endpoint de analytics agregado — primeiro valor visível para o usuário.
"""
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import text as sql_text

from src.database import AsyncSessionFactory

router = APIRouter()


@router.get("/summary")
async def analytics_summary(
    shop_domain: Optional[str] = Query(
        default=None, description="Filtrar por loja (shop_domain)"
    ),
):
    """
    Resumo executivo do pipeline de dados.
    shop_domain: opcional — se fornecido, filtra conversões da loja específica.
    """
    shop_filter = ""
    shop_params: dict = {}
    if shop_domain:
        shop_filter = (
            "AND ac.id IN (SELECT conversion_id FROM shopify_orders "
            "WHERE shop_domain = :shop_domain AND conversion_id IS NOT NULL)"
        )
        shop_params = {"shop_domain": shop_domain}

    async with AsyncSessionFactory() as session:
        profiles = await session.execute(
            sql_text("SELECT COUNT(*) FROM identity_profiles")
        )
        total_profiles = profiles.scalar()

        orders_q = (
            "SELECT COUNT(*) FROM shopify_orders "
            "WHERE created_at >= NOW() - INTERVAL '30 days'"
        )
        if shop_domain:
            orders_q += " AND shop_domain = :shop_domain"
        shopify_count = await session.execute(sql_text(orders_q), shop_params)

        conv_q = f"""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(ac.revenue), 0) AS total_revenue,
                   ac.currency
            FROM attribution_conversions ac
            WHERE ac.occurred_at >= NOW() - INTERVAL '30 days'
            {shop_filter}
            GROUP BY ac.currency
            ORDER BY total_revenue DESC
            LIMIT 1
        """
        conversions = await session.execute(sql_text(conv_q), shop_params)
        conv_row = conversions.fetchone()

        channel_q = f"""
            SELECT ar.channel,
                   COUNT(DISTINCT ar.conversion_id) AS conversions,
                   ROUND(SUM(ar.revenue_credit)::numeric, 2) AS revenue_credit
            FROM attribution_results ar
            JOIN attribution_conversions ac ON ac.id = ar.conversion_id
            WHERE ar.model = 'linear'
              AND ac.occurred_at >= NOW() - INTERVAL '30 days'
            {shop_filter}
            GROUP BY ar.channel
            ORDER BY revenue_credit DESC
            LIMIT 10
        """
        by_channel = await session.execute(sql_text(channel_q), shop_params)
        channels = by_channel.fetchall()

        ltv_q = f"""
            SELECT ac.profile_id,
                   COUNT(*) AS conversions,
                   ROUND(SUM(ac.revenue)::numeric, 2) AS ltv
            FROM attribution_conversions ac
            WHERE ac.occurred_at >= NOW() - INTERVAL '30 days'
            {shop_filter}
            GROUP BY ac.profile_id
            ORDER BY ltv DESC
            LIMIT 5
        """
        top_ltv = await session.execute(sql_text(ltv_q), shop_params)
        ltv_rows = top_ltv.fetchall()

    return {
        "period": "last_30_days",
        "shop_domain": shop_domain,
        "profiles": {"total": total_profiles},
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


@router.get("/usage")
async def usage_stats(
    shop_domain: Optional[str] = Query(default=None),
    seller_id: Optional[str] = Query(default=None),
):
    """
    Retorna uso do mês corrente para uma loja.
    Usado pelo VERTEX para mostrar barra de progresso de uso.
    """
    async with AsyncSessionFactory() as session:
        shopify_count = 0
        tray_count = 0

        if shop_domain:
            r = await session.execute(
                sql_text("""
                    SELECT COUNT(*) FROM shopify_orders
                    WHERE shop_domain = :domain
                      AND created_at >= DATE_TRUNC('month', NOW())
                """),
                {"domain": shop_domain},
            )
            shopify_count = r.scalar() or 0

        if seller_id:
            r = await session.execute(
                sql_text("""
                    SELECT COUNT(*) FROM tray_orders
                    WHERE seller_id = :seller_id
                      AND created_at >= DATE_TRUNC('month', NOW())
                """),
                {"seller_id": seller_id},
            )
            tray_count = r.scalar() or 0

    total = shopify_count + tray_count
    return {
        "period": "current_month",
        "shop_domain": shop_domain,
        "seller_id": seller_id,
        "shopify_orders": shopify_count,
        "tray_orders": tray_count,
        "total_orders": total,
        "free_limit": 100,
        "within_limit": total < 100,
    }
