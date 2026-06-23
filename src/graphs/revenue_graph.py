import asyncio
import logging

from src.graphs.connection import execute_cypher

logger = logging.getLogger(__name__)

GRAPH = "revenue_graph"


def upsert_identity_node(profile_id: str, is_known: bool = False) -> None:
    """Cria ou atualiza nó Identity."""
    execute_cypher(f"""
        SELECT * FROM cypher('{GRAPH}', $$
            MERGE (i:Identity {{id: '{profile_id}'}})
            SET i.is_known = {str(is_known).lower()}, i.updated_at = timestamp()
            RETURN i
        $$) AS (i agtype)
    """)


def upsert_campaign_node(campaign_id: str, channel: str) -> None:
    """Cria ou atualiza nó Campaign."""
    execute_cypher(f"""
        SELECT * FROM cypher('{GRAPH}', $$
            MERGE (c:Campaign {{id: '{campaign_id}'}})
            SET c.channel = '{channel}', c.updated_at = timestamp()
            RETURN c
        $$) AS (c agtype)
    """)


def upsert_conversion_node(
    conversion_id: str,
    profile_id: str,
    revenue: float,
    currency: str,
) -> None:
    """Cria nó Conversion e edge CONVERTED de Identity."""
    execute_cypher(f"""
        SELECT * FROM cypher('{GRAPH}', $$
            MERGE (conv:Conversion {{id: '{conversion_id}'}})
            SET conv.revenue = {revenue}, conv.currency = '{currency}', conv.updated_at = timestamp()
            RETURN conv
        $$) AS (conv agtype)
    """)
    execute_cypher(f"""
        SELECT * FROM cypher('{GRAPH}', $$
            MATCH (i:Identity {{id: '{profile_id}'}}), (conv:Conversion {{id: '{conversion_id}'}})
            MERGE (i)-[:CONVERTED]->(conv)
            RETURN i, conv
        $$) AS (i agtype, conv agtype)
    """)


def link_campaign_to_conversion(
    campaign_id: str,
    conversion_id: str,
    model: str,
    credit: float,
    revenue_credit: float,
) -> None:
    """Cria edge GENERATED de Campaign para Conversion."""
    execute_cypher(f"""
        SELECT * FROM cypher('{GRAPH}', $$
            MATCH (camp:Campaign {{id: '{campaign_id}'}}), (conv:Conversion {{id: '{conversion_id}'}})
            MERGE (camp)-[r:GENERATED {{model: '{model}'}}]->(conv)
            SET r.credit = {credit}, r.revenue_credit = {revenue_credit}
            RETURN camp, r, conv
        $$) AS (camp agtype, r agtype, conv agtype)
    """)


def query_revenue_by_channel(model: str = "linear", limit: int = 10) -> list[dict]:
    """Retorna receita total atribuída por canal para um modelo de atribuição."""
    rows = execute_cypher(f"""
        SELECT * FROM cypher('{GRAPH}', $$
            MATCH (camp:Campaign)-[r:GENERATED {{model: '{model}'}}]->(conv:Conversion)
            RETURN
                camp.channel         AS channel,
                count(conv)          AS conversions,
                sum(r.revenue_credit) AS total_revenue
            ORDER BY sum(r.revenue_credit) DESC
            LIMIT {limit}
        $$) AS (channel agtype, conversions agtype, total_revenue agtype)
    """)
    return [
        {
            "channel": str(r["channel"]).strip('"'),
            "conversions": int(str(r["conversions"])),
            "total_revenue": float(str(r["total_revenue"])),
        }
        for r in rows
    ]


def query_identity_ltv(min_revenue: float = 0.0, limit: int = 10) -> list[dict]:
    """Retorna identidades ordenadas por LTV (soma de revenue das conversões)."""
    rows = execute_cypher(f"""
        SELECT * FROM cypher('{GRAPH}', $$
            MATCH (i:Identity)-[:CONVERTED]->(conv:Conversion)
            WHERE conv.revenue > {min_revenue}
            RETURN
                i.id              AS identity_id,
                count(conv)       AS total_conversions,
                sum(conv.revenue) AS ltv
            ORDER BY sum(conv.revenue) DESC
            LIMIT {limit}
        $$) AS (identity_id agtype, total_conversions agtype, ltv agtype)
    """)
    return [
        {
            "identity_id": str(r["identity_id"]).strip('"'),
            "total_conversions": int(str(r["total_conversions"])),
            "ltv": float(str(r["ltv"])),
        }
        for r in rows
    ]


async def sync_attribution_to_graph(
    profile_id: str,
    conversion_id: str,
    revenue: float,
    currency: str,
    attribution_results: list[dict],
) -> None:
    """
    Sincroniza resultados de atribuição para o Revenue Graph.
    Chamado após cada /compute bem-sucedido.
    """
    try:
        await asyncio.to_thread(upsert_identity_node, profile_id)
        await asyncio.to_thread(upsert_conversion_node, conversion_id, profile_id, revenue, currency)

        for r in attribution_results:
            if r.get("campaign_id"):
                await asyncio.to_thread(upsert_campaign_node, r["campaign_id"], r["channel"])
                await asyncio.to_thread(
                    link_campaign_to_conversion,
                    r["campaign_id"],
                    conversion_id,
                    r["model"],
                    r["credit"],
                    r.get("revenue_credit", 0.0),
                )
        logger.info("Graph sync OK: conversion %s", conversion_id)
    except Exception as e:
        logger.error("Graph sync FAILED for conversion %s: %s", conversion_id, e)
