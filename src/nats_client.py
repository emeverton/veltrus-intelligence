import json

from typing import Optional

import nats
from nats.aio.client import Client as NATSClient

from src.config import settings

_nc: Optional[NATSClient] = None


async def get_nats() -> NATSClient:
    global _nc
    if _nc is None or not _nc.is_connected:
        _nc = await nats.connect(settings.nats_url)
    return _nc


async def publish(subject: str, payload: dict) -> None:
    nc = await get_nats()
    js = nc.jetstream()
    await js.publish(subject, json.dumps(payload).encode())


async def close_nats() -> None:
    global _nc
    if _nc and _nc.is_connected:
        await _nc.close()
        _nc = None
