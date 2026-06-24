import asyncio
import logging

import httpx

from src.config import settings
from src.gpu.vast_client import (
    create_instance_from_offer,
    destroy_instance,
    find_best_offer,
    get_instance_ports,
    list_instances,
)

logger = logging.getLogger(__name__)
_current_instance_id: int | None = None
_inference_url: str | None = None
_llm_url: str | None = None


async def get_inference_url() -> str | None:
    """URL do FastAPI inference server (FLUX, porta 8080)."""
    global _inference_url, _current_instance_id, _llm_url

    if _inference_url:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{_inference_url}/health")
                if r.status_code == 200:
                    return _inference_url
        except Exception:
            _inference_url = None
            _llm_url = None

    instances = await list_instances()
    running = [
        i for i in instances
        if i.get("actual_status") == "running"
        and i.get("label") == "veltrus-intelligence-gpu"
    ]
    if not running:
        return None

    inst = running[0]
    _current_instance_id = inst["id"]
    ports = await get_instance_ports(_current_instance_id)
    _inference_url = ports.get("8080/tcp")
    _llm_url = ports.get("8081/tcp")
    if _inference_url:
        logger.info("GPU inference URL: %s", _inference_url)
    return _inference_url


async def get_llm_url() -> str | None:
    """URL do vLLM server (Qwen 7B, porta 8081). None se GPU offline."""
    await get_inference_url()
    return _llm_url


async def start_gpu(
    wait_for_ready: bool = True,
    timeout_seconds: int = 300,
) -> dict:
    """Inicia uma instância GPU no Vast.ai."""
    global _current_instance_id

    existing_url = await get_inference_url()
    if existing_url:
        return {
            "status": "already_running",
            "inference_url": existing_url,
            "llm_url": _llm_url,
        }

    if not settings.vastai_api_key:
        return {"status": "failed", "error": "VASTAI_API_KEY not configured"}

    if settings.vastai_offer_id:
        offer_id = settings.vastai_offer_id
    else:
        offer = await find_best_offer()
        if not offer:
            return {
                "status": "failed",
                "error": "No RTX 4090 offer available under $0.80/hr",
            }
        offer_id = offer["id"]

    logger.info("Starting GPU instance from offer %s", offer_id)
    result = await create_instance_from_offer(
        offer_id=offer_id,
        image=settings.gpu_inference_image,
        hf_token=settings.hf_token,
    )
    _current_instance_id = result.get("new_contract")

    if not wait_for_ready:
        return {"status": "starting", "instance_id": _current_instance_id}

    url = await _wait_for_ready_internal(timeout_seconds)
    if url:
        return {"status": "started", "inference_url": url, "llm_url": _llm_url}
    return {"status": "timeout", "instance_id": _current_instance_id}


async def stop_gpu() -> dict:
    """Para e destrói a instância GPU atual."""
    global _current_instance_id, _inference_url, _llm_url

    if not _current_instance_id:
        instances = await list_instances()
        veltrus = [i for i in instances if i.get("label") == "veltrus-intelligence-gpu"]
        if not veltrus:
            return {"status": "not_running"}
        _current_instance_id = veltrus[0]["id"]

    destroyed = await destroy_instance(_current_instance_id)
    _current_instance_id = None
    _inference_url = None
    _llm_url = None
    return {"status": "stopped" if destroyed else "error"}


async def wait_for_ready(timeout_seconds: int = 120) -> str | None:
    """Aguarda até o inference server responder /health."""
    return await _wait_for_ready_internal(timeout_seconds)


async def stop_current_instance() -> bool:
    """Legacy wrapper — prefer stop_gpu()."""
    result = await stop_gpu()
    return result.get("status") == "stopped"


async def _wait_for_ready_internal(timeout: int) -> str | None:
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < timeout:
        url = await get_inference_url()
        if url:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    r = await client.get(f"{url}/health")
                    if r.status_code == 200:
                        logger.info("GPU server ready at %s", url)
                        return url
            except Exception:
                pass
        await asyncio.sleep(10)
    logger.error("GPU server did not become ready in %ss", timeout)
    return None
