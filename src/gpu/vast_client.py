import httpx
import logging

from src.config import settings

logger = logging.getLogger(__name__)
BASE_URL = "https://console.vast.ai/api/v0"


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.vastai_api_key}"}


async def list_instances() -> list[dict]:
    """Lista instâncias GPU do usuário."""
    if not settings.vastai_api_key:
        logger.debug("VASTAI_API_KEY not configured — skipping instance lookup")
        return []
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE_URL}/instances/", headers=_headers())
        r.raise_for_status()
        return r.json().get("instances", [])


async def start_instance(offer_id: int, image: str, disk_gb: float = 30.0) -> dict:
    """
    Cria e inicia uma instância Vast.ai a partir de um offer_id.
    """
    if not settings.vastai_api_key:
        raise RuntimeError("VASTAI_API_KEY not configured")
    payload = {
        "client_id": "me",
        "image": image,
        "disk": disk_gb,
        "onstart": "cd /app && uvicorn main:app --host 0.0.0.0 --port 8080 &",
        "env": {
            "HF_TOKEN": settings.hf_token or "",
        },
        "extra_env": {},
        "runtype": "ssh",
        "use_jupyter_lab": False,
        "jupyter_token": "",
        "template_hash_id": None,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.put(f"{BASE_URL}/asks/{offer_id}/", headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()


async def destroy_instance(instance_id: int) -> bool:
    """Para e destrói a instância."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.delete(f"{BASE_URL}/instances/{instance_id}/", headers=_headers())
        return r.status_code in (200, 204)


async def get_instance_info(instance_id: int) -> dict | None:
    """Retorna info da instância (IP, porta, status)."""
    instances = await list_instances()
    for inst in instances:
        if inst.get("id") == instance_id:
            return inst
    return None
