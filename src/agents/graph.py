import asyncio
import json
import logging
import operator
from typing import Annotated, Optional, TypedDict

import anthropic
from langgraph.graph import END, StateGraph

from src.agents.tool_executor import execute_tool
from src.agents.tools import TOOLS
from src.config import settings
from src.gpu.llm_client import (
    anthropic_tools_to_openai,
    chat_completion as qwen_chat,
    anthropic_to_openai_messages,
)

logger = logging.getLogger(__name__)
_anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
_openai_tools = anthropic_tools_to_openai(TOOLS)

MAX_ITERATIONS = 6

SYSTEM_PROMPT = (
    "Você é um Revenue Intelligence Agent da Veltrus. "
    "Analise dados de marketing, atribuição e identidade para gerar insights acionáveis. "
    "Use as tools disponíveis para obter dados reais antes de responder. "
    "Responda sempre em português, de forma objetiva e técnica."
)


class TextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class ToolUseBlock:
    def __init__(self, block_id: str, name: str, tool_input: dict):
        self.type = "tool_use"
        self.id = block_id
        self.name = name
        self.input = tool_input


class AgentState(TypedDict):
    task: str
    messages: Annotated[list, operator.add]
    iteration: int
    result: Optional[str]


async def _call_llm_with_fallback(messages: list[dict]) -> tuple[str, list]:
    """
    Tenta Qwen 7B primeiro (GPU). Fallback para Claude API se GPU offline.
    Retorna (provider_used, response_content_blocks).
    """
    try:
        oai_messages = anthropic_to_openai_messages(messages)
        response = await qwen_chat(oai_messages, tools=_openai_tools)
        msg = response["choices"][0]["message"]

        content_blocks = []
        if msg.get("content"):
            content_blocks.append(TextBlock(msg["content"]))
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                content_blocks.append(
                    ToolUseBlock(
                        tc["id"],
                        tc["function"]["name"],
                        json.loads(tc["function"]["arguments"]),
                    )
                )
        return "qwen", content_blocks

    except RuntimeError:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "GPU offline e ANTHROPIC_API_KEY não configurada — nenhum LLM disponível"
            ) from None

        response = await asyncio.to_thread(
            _anthropic_client.messages.create,
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=TOOLS,
        )
        return "claude", response.content


async def reasoning_node(state: AgentState) -> AgentState:
    """Dual-mode LLM com tool_use. Qwen se GPU online, Claude fallback."""
    logger.info(
        "Agent reasoning iteration %s — task: %s",
        state["iteration"],
        state["task"][:80],
    )

    provider, content = await _call_llm_with_fallback(state["messages"])
    logger.info("LLM provider used: %s", provider)

    assistant_message = {"role": "assistant", "content": content}
    has_tool_call = any(getattr(b, "type", None) == "tool_use" for b in content)

    if not has_tool_call or state["iteration"] >= MAX_ITERATIONS:
        text_blocks = [b.text for b in content if hasattr(b, "text")]
        final_text = "\n".join(text_blocks) or "Análise concluída."
        return {
            "messages": [assistant_message],
            "iteration": state["iteration"] + 1,
            "result": final_text,
        }

    return {
        "messages": [assistant_message],
        "iteration": state["iteration"] + 1,
        "result": None,
    }


async def tool_node(state: AgentState) -> AgentState:
    """Executa todas as tools chamadas pelo LLM na última mensagem."""
    last_message = state["messages"][-1]
    tool_results = []

    for block in last_message["content"]:
        block_type = getattr(block, "type", None)
        if block_type != "tool_use":
            continue
        logger.info(
            "Executing tool: %s input=%s",
            block.name,
            json.dumps(block.input)[:100],
        )
        result_text = await execute_tool(block.name, block.input)
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": result_text,
        })

    user_tool_result = {"role": "user", "content": tool_results}
    return {"messages": [user_tool_result]}


def should_continue(state: AgentState) -> str:
    """Router: continua se resultado ainda não chegou, termina se chegou."""
    if state.get("result") is not None:
        return END
    if state["iteration"] >= MAX_ITERATIONS:
        return END
    if state["messages"]:
        last = state["messages"][-1]
        content = last.get("content")
        if isinstance(content, list):
            if any(getattr(b, "type", None) == "tool_use" for b in content):
                return "tool_node"
    return END


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("reasoning", reasoning_node)
    graph.add_node("tool_node", tool_node)
    graph.set_entry_point("reasoning")
    graph.add_conditional_edges(
        "reasoning",
        should_continue,
        {END: END, "tool_node": "tool_node"},
    )
    graph.add_edge("tool_node", "reasoning")
    return graph.compile()


AGENT = build_agent_graph()


async def run_agent(task: str, context: Optional[dict] = None) -> str:
    """Ponto de entrada para rodar o agente. Retorna string com a análise final."""
    initial_message = {"role": "user", "content": task}
    if context:
        initial_message["content"] += (
            f"\n\nContexto adicional: {json.dumps(context, ensure_ascii=False)}"
        )

    initial_state: AgentState = {
        "task": task,
        "messages": [initial_message],
        "iteration": 0,
        "result": None,
    }

    final_state = await AGENT.ainvoke(initial_state)
    return final_state.get("result") or "Agente não retornou resultado."
