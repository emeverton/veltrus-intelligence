import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_gpu_health_offline():
    """Sem instâncias ativas: retorna offline."""
    with patch("src.gpu.vast_client.list_instances", AsyncMock(return_value=[])):
        from src.gpu.generate_client import gpu_health

        result = await gpu_health()
    assert result["status"] == "offline"


@pytest.mark.asyncio
async def test_generate_image_raises_when_gpu_offline():
    """generate_image lança RuntimeError se GPU offline."""
    with patch("src.gpu.instance_manager.get_inference_url", AsyncMock(return_value=None)):
        from src.gpu.generate_client import generate_image

        with pytest.raises(RuntimeError, match="offline"):
            await generate_image("test prompt")


def test_tools_include_gpu_tools():
    """Verificar que tools de geração foram adicionadas."""
    from src.agents.tools import TOOLS

    tool_names = [t["name"] for t in TOOLS]
    assert "generate_image" in tool_names
    assert "synthesize_voice" in tool_names
    assert "gpu_status" in tool_names


@pytest.mark.asyncio
async def test_kokoro_not_available_raises_runtime_error():
    """Se kokoro-onnx não instalado: RuntimeError descritivo."""
    with patch("src.voice.kokoro._get_kokoro", return_value=None):
        from src.voice.kokoro import synthesize_async

        with pytest.raises(RuntimeError, match="not available"):
            await synthesize_async("teste")
