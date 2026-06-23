import json
import logging
import operator
from typing import Annotated, Optional, TypedDict

import anthropic
from langgraph.graph import END, StateGraph

from src.agents.tool_executor import execute_tool
from src.agents.tools import TOOLS
from src.config import settings

logger = logging.getLogger(__name__)
_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

MAX_ITERATIONS = 6


class AgentState(TypedDict):
    task: str
    messages: Annotated[list, operator.add]
    iteration: int
    result: Optional[str]


async def reasoning_node(state: AgentState) -> AgentState:
    """Claude API com tool_use. Retorna mensagem com texto ou tool_use blocks."""
    logger.info(
        "Agent reasoning iteration %s — task: %s",
        state["iteration"],
        state["task"][:80],
    )

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=(
            "Você é um Revenue Intelligence Agent da Veltrus. "
            "Analise dados de marketing, atribuição e identidade para gerar insights acionáveis. "
            "Use as tools disponíveis para obter dados reais antes de responder. "
            "Responda sempre em português, de forma objetiva e técnica."
        ),
        messages=state["messages"],
        tools=TOOLS,
    )

    assistant_message = {"role": "assistant", "content": response.content}
    has_tool_call = any(block.type == "tool_use" for block in response.content)

    if not has_tool_call or state["iteration"] >= MAX_ITERATIONS:
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        final_text = "\n".join(text_blocks) or "Análise concluída sem resposta textual."
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
    """Executa todas as tools chamadas pelo Claude na última mensagem."""
    last_message = state["messages"][-1]
    tool_results = []

    for block in last_message["content"]:
        if block.type != "tool_use":
            continue
        logger.info("Executing tool: %s input=%s", block.name, json.dumps(block.input)[:100])
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
