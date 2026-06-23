import asyncio
import json

import httpx

from src.agents.forecast import forecast_revenue_async
from src.embeddings.model import encode_text_async
from src.embeddings.qdrant_ops import search_similar_async
from src.graphs.revenue_graph import query_identity_ltv, query_revenue_by_channel


async def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Executa uma tool e retorna resultado como string JSON."""
    try:
        if tool_name == "query_revenue_by_channel":
            result = await asyncio.to_thread(
                query_revenue_by_channel,
                tool_input.get("model", "linear"),
                tool_input.get("limit", 10),
            )
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "query_identity_ltv":
            result = await asyncio.to_thread(
                query_identity_ltv,
                tool_input.get("min_revenue", 0.0),
                tool_input.get("limit", 10),
            )
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "search_creatives":
            vector = await encode_text_async(tool_input["query"])
            result = await search_similar_async(
                vector,
                limit=tool_input.get("limit", 5),
                channel_filter=tool_input.get("channel"),
            )
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "forecast_revenue":
            result = await forecast_revenue_async(
                days=tool_input.get("days", 30),
                channel=tool_input.get("channel"),
            )
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "get_attribution_report":
            profile_id = tool_input["profile_id"]
            model_param = f"?model={tool_input['model']}" if tool_input.get("model") else ""
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://localhost:8001/api/v1/attribution/report/{profile_id}{model_param}"
                )
                return resp.text

        return json.dumps({"error": f"Tool '{tool_name}' not implemented"})

    except Exception as e:
        return json.dumps({"error": str(e), "tool": tool_name})
