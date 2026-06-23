import asyncio
import logging

import httpx

from src.gpu.vast_client import destroy_instance, list_instances

logger = logging.getLogger(__name__)
_current_instance_id: int | None = None
_inference_url: str | None = None


async def get_inference_url() -> str | None:
    """Retorna URL do inference server se instância está ativa e saudável."""
    global _inference_url, _current_instance_id

    if _inference_url:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{_inference_url}/health")
                if r.status_code == 200:
                    return _inference_url
        except Exception:
            logger.warning("GPU inference server health check failed — instance may be down")
            _inference_url = None
            _current_instance_id = None

    instances = await list_instances()
    running = [i for i in instances if i.get("actual_status") == "running"]
    if not running:
        return None

    inst = running[0]
    _current_instance_id = inst["id"]

    host = inst.get("ssh_host") or inst.get("public_ipaddr")
    port_mappings = inst.get("ports", {})
    external_port = (
        port_mappings.get("8080/tcp", [{}])[0].get("HostPort", "8080")
        if port_mappings
        else "8080"
    )

    _inference_url = f"http://{host}:{external_port}"
    logger.info("GPU inference URL: %s", _inference_url)
    return _inference_url


async def wait_for_ready(timeout_seconds: int = 120) -> str | None:
    """Aguarda até o inference server responder /health."""
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < timeout_seconds:
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
        await asyncio.sleep(5)
    logger.error("GPU server did not become ready in %ss", timeout_seconds)
    return None


async def stop_current_instance() -> bool:
    """Para a instância atual se existir."""
    global _current_instance_id, _inference_url
    if _current_instance_id:
        result = await destroy_instance(_current_instance_id)
        _current_instance_id = None
        _inference_url = None
        return result
    return False
