import httpx
import logging

from src.gpu.instance_manager import get_inference_url

logger = logging.getLogger(__name__)
TIMEOUT = 120


async def generate_image(prompt: str, width: int = 768, height: int = 768) -> dict:
    """
    Envia request de geração de imagem ao inference server GPU.
    Retorna dict com data_base64 (PNG).
    Lança RuntimeError se GPU offline.
    """
    url = await get_inference_url()
    if not url:
        raise RuntimeError("GPU inference server offline. Inicie a instância Vast.ai primeiro.")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{url}/generate/image",
            json={
                "prompt": prompt,
                "width": width,
                "height": height,
                "steps": 4,
            },
        )
        r.raise_for_status()
        return r.json()


async def generate_video(prompt: str, duration_seconds: float = 3.0) -> dict:
    """Gera vídeo via Wan 2.1. GPU online necessária."""
    url = await get_inference_url()
    if not url:
        raise RuntimeError("GPU offline.")

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            f"{url}/generate/video",
            json={
                "prompt": prompt,
                "duration_seconds": duration_seconds,
            },
        )
        r.raise_for_status()
        return r.json()


async def gpu_health() -> dict:
    """Status do inference server GPU."""
    url = await get_inference_url()
    if not url:
        return {"status": "offline", "url": None}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{url}/health")
            data = r.json()
            data["url"] = url
            return data
    except Exception as e:
        return {"status": "error", "error": str(e), "url": url}
