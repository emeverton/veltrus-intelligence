import asyncio
import logging
from typing import Optional

from src.graphs.connection import execute_cypher

logger = logging.getLogger(__name__)
GRAPH = "revenue_graph"


def upsert_creative_node(creative_id: str, channel: str, creative_type: str) -> None:
    """Cria ou atualiza nó Creative. Padrão AGE correto: MERGE + SET."""
    execute_cypher(f"""
        SELECT * FROM cypher('{GRAPH}', $$
            MERGE (cr:Creative {{id: '{creative_id}'}})
            SET cr.channel = '{channel}'
            SET cr.creative_type = '{creative_type}'
            RETURN cr
        $$) AS (cr agtype)
    """)


def link_creative_to_campaign(creative_id: str, campaign_id: str) -> None:
    """Edge USED_IN: Creative → Campaign. Props SET após MERGE."""
    execute_cypher(f"""
        SELECT * FROM cypher('{GRAPH}', $$
            MATCH (cr:Creative {{id: '{creative_id}'}}),
                  (camp:Campaign {{id: '{campaign_id}'}})
            MERGE (cr)-[r:USED_IN]->(camp)
            SET r.linked_at = timestamp()
            RETURN cr, r, camp
        $$) AS (cr agtype, r agtype, camp agtype)
    """)


def query_top_creatives_by_revenue(limit: int = 10) -> list[dict]:
    """Criativos com maior revenue atribuído via campanha → conversão."""
    rows = execute_cypher(f"""
        SELECT * FROM cypher('{GRAPH}', $$
            MATCH (cr:Creative)-[:USED_IN]->(camp:Campaign)-[g:GENERATED]->(conv:Conversion)
            RETURN
                cr.id                   AS creative_id,
                cr.channel              AS channel,
                count(conv)             AS conversions,
                sum(g.revenue_credit)   AS total_revenue
            ORDER BY sum(g.revenue_credit) DESC
            LIMIT {limit}
        $$) AS (creative_id agtype, channel agtype, conversions agtype, total_revenue agtype)
    """)
    return [
        {
            "creative_id": str(r["creative_id"]).strip('"'),
            "channel": str(r["channel"]).strip('"'),
            "conversions": int(str(r["conversions"] or 0)),
            "total_revenue": float(str(r["total_revenue"] or 0)),
        }
        for r in rows
    ]


async def sync_creative_to_graph(
    creative_id: str,
    channel: str,
    creative_type: str,
    campaign_id: Optional[str],
) -> None:
    """Sync fire-and-forget: cria nó Creative e edge USED_IN se campaign_id disponível."""
    try:
        await asyncio.to_thread(upsert_creative_node, creative_id, channel, creative_type)
        if campaign_id:
            await asyncio.to_thread(link_creative_to_campaign, creative_id, campaign_id)
        logger.info("Creative graph sync OK: %s", creative_id)
    except Exception as e:
        logger.error("Creative graph sync FAILED for %s: %s", creative_id, e)
