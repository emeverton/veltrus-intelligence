import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_anthropic_to_openai_messages_string():
    from src.gpu.llm_client import anthropic_to_openai_messages

    msgs = [{"role": "user", "content": "qual canal gerou mais receita?"}]
    result = anthropic_to_openai_messages(msgs)
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "qual canal gerou mais receita?"


def test_anthropic_tools_to_openai():
    from src.gpu.llm_client import anthropic_tools_to_openai
    from src.agents.tools import TOOLS

    oai = anthropic_tools_to_openai(TOOLS)
    assert all(t["type"] == "function" for t in oai)
    assert all("name" in t["function"] for t in oai)
    assert len(oai) == len(TOOLS)


@pytest.mark.asyncio
async def test_fallback_to_claude_when_gpu_offline():
    """Quando GPU offline, deve usar Claude API sem lançar erro."""
    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Resposta Claude"
    mock_response = MagicMock()
    mock_response.content = [mock_text_block]

    with patch("src.agents.graph.qwen_chat", AsyncMock(side_effect=RuntimeError("GPU offline"))), \
         patch("src.agents.graph._anthropic_client") as mock_claude, \
         patch("src.agents.graph.asyncio.to_thread", AsyncMock(return_value=mock_response)):
        mock_claude.messages.create.return_value = mock_response

        from src.agents.graph import _call_llm_with_fallback

        provider, content = await _call_llm_with_fallback([{"role": "user", "content": "teste"}])

    assert provider == "claude"


@pytest.mark.asyncio
async def test_prefers_qwen_when_gpu_online():
    """Quando GPU online, deve usar Qwen — não Claude."""
    mock_response = {
        "choices": [{"message": {"content": "Resposta Qwen", "tool_calls": None}}]
    }
    with patch("src.agents.graph.qwen_chat", AsyncMock(return_value=mock_response)):
        from src.agents.graph import _call_llm_with_fallback

        provider, _content = await _call_llm_with_fallback([{"role": "user", "content": "teste"}])

    assert provider == "qwen"


@pytest.mark.asyncio
async def test_gpu_start_no_api_key():
    """Sem VASTAI_API_KEY configurada: retornar erro descritivo, não 500."""
    with patch("src.gpu.instance_manager.settings") as mock_settings:
        mock_settings.vastai_api_key = ""
        mock_settings.vastai_offer_id = 0
        mock_settings.gpu_inference_image = "veltrus-intelligence-gpu:latest"
        mock_settings.hf_token = ""
        from src.gpu.instance_manager import start_gpu

        result = await start_gpu(wait_for_ready=False)
    assert result["status"] == "failed"
    assert "VASTAI_API_KEY" in result["error"]
