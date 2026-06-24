"""
Cliente para o vLLM server rodando Qwen 2.5 7B no Vast.ai.
Compatível com OpenAI API format — mesmos endpoints, mesmos parâmetros.
"""
import json
import logging

import httpx

from src.gpu.instance_manager import get_llm_url

logger = logging.getLogger(__name__)
QWEN_MODEL = "Qwen/Qwen2.5-7B-Instruct"


async def chat_completion(
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 2048,
) -> dict:
    """
    Chama o vLLM server com formato OpenAI.
    Retorna resposta no formato OpenAI ChatCompletion.
    Lança RuntimeError se GPU offline.
    """
    url = await get_llm_url()
    if not url:
        raise RuntimeError("GPU LLM offline — Qwen 7B indisponível")

    payload: dict = {
        "model": QWEN_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{url}/v1/chat/completions", json=payload)
        r.raise_for_status()
        return r.json()


def _block_type(block) -> str | None:
    if isinstance(block, dict):
        return block.get("type")
    return getattr(block, "type", None)


def anthropic_to_openai_messages(anthropic_messages: list[dict]) -> list[dict]:
    """Converte mensagens do formato Anthropic para formato OpenAI."""
    result = []
    for msg in anthropic_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            result.append({"role": role, "content": str(content)})
            continue

        if role == "user" and any(_block_type(b) == "tool_result" for b in content):
            for block in content:
                if _block_type(block) != "tool_result":
                    continue
                if isinstance(block, dict):
                    result.append({
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": block.get("content", ""),
                    })
                else:
                    result.append({
                        "role": "tool",
                        "tool_call_id": block.tool_use_id,
                        "content": getattr(block, "content", ""),
                    })
            continue

        text_parts = []
        tool_calls = []
        for block in content:
            block_type = _block_type(block)
            if block_type == "text":
                text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                text_parts.append(text)
            elif block_type == "tool_use":
                if isinstance(block, dict):
                    bid, name, inp = block["id"], block["name"], block.get("input", {})
                else:
                    bid, name, inp = block.id, block.name, block.input
                tool_calls.append({
                    "id": bid,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(inp)},
                })

        if role == "assistant" and tool_calls:
            result.append({
                "role": "assistant",
                "content": " ".join(text_parts) or None,
                "tool_calls": tool_calls,
            })
        else:
            result.append({"role": role, "content": " ".join(text_parts) or ""})
    return result


def anthropic_tools_to_openai(tools: list[dict]) -> list[dict]:
    """Converte tool definitions do formato Anthropic para OpenAI."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]
