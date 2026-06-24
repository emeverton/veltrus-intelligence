import json
import logging

import httpx

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


async def find_best_offer(
    gpu_name: str = "RTX 4090",
    min_vram_gb: int = 24,
    max_price_per_hour: float = 0.80,
) -> dict | None:
    """Busca o offer mais barato disponível com o GPU especificado."""
    if not settings.vastai_api_key:
        return None
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE_URL}/bundles/",
            headers=_headers(),
            params={
                "q": json.dumps({
                    "gpu_name": {"eq": gpu_name},
                    "rentable": {"eq": True},
                    "num_gpus": {"eq": 1},
                    "dph_total": {"lte": max_price_per_hour},
                }),
                "order": "dph_total asc",
                "limit": 1,
            },
        )
        r.raise_for_status()
        offers = r.json().get("offers", [])
        return offers[0] if offers else None


async def create_instance_from_offer(
    offer_id: int,
    image: str,
    hf_token: str = "",
    disk_gb: float = 40.0,
) -> dict:
    """Cria instância a partir de um offer_id com configurações de startup."""
    if not settings.vastai_api_key:
        raise RuntimeError("VASTAI_API_KEY not configured")
    payload = {
        "client_id": "me",
        "image": image,
        "disk": disk_gb,
        "label": "veltrus-intelligence-gpu",
        "extra_env": {
            "HF_TOKEN": hf_token,
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
        },
        "onstart": (
            "cd /app && "
            "python -m vllm.entrypoints.openai.api_server "
            "--model Qwen/Qwen2.5-7B-Instruct "
            "--port 8081 "
            "--dtype bfloat16 "
            "--max-model-len 8192 "
            "--gpu-memory-utilization 0.35 & "
            "sleep 30 && uvicorn main:app --host 0.0.0.0 --port 8080 & "
            "wait"
        ),
        "runtype": "args",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.put(
            f"{BASE_URL}/asks/{offer_id}/",
            headers=_headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()


async def start_instance(offer_id: int, image: str, disk_gb: float = 30.0) -> dict:
    """Legacy wrapper — prefer create_instance_from_offer."""
    return await create_instance_from_offer(offer_id, image, settings.hf_token, disk_gb)


async def destroy_instance(instance_id: int) -> bool:
    """Para e destrói a instância."""
    if not settings.vastai_api_key:
        return False
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


async def get_instance_ports(instance_id: int) -> dict[str, str]:
    """Retorna mapeamento de portas da instância {porto_interno: url}."""
    info = await get_instance_info(instance_id)
    if not info:
        return {}
    ports = info.get("ports", {})
    host = info.get("ssh_host") or info.get("public_ipaddr", "")
    result = {}
    for internal, mappings in ports.items():
        if mappings:
            result[internal] = f"http://{host}:{mappings[0].get('HostPort')}"
    return result
