import json
import logging
from typing import Optional

import nats
from nats.aio.client import Client as NATSClient
from nats.js.api import StreamConfig

from src.config import settings

logger = logging.getLogger(__name__)

_nc: Optional[NATSClient] = None
ATTRIBUTION_STREAM = "attribution"
ATTRIBUTION_SUBJECTS = ["attribution.>"]
AGENTS_STREAM = "agents"
AGENTS_SUBJECTS = ["agents.>"]


async def get_nats() -> NATSClient:
    global _nc
    if _nc is None or not _nc.is_connected:
        _nc = await nats.connect(settings.nats_url)
    return _nc


async def ensure_attribution_stream() -> None:
    """Garante stream JetStream antes de publish/subscribe."""
    nc = await get_nats()
    js = nc.jetstream()
    try:
        await js.add_stream(
            StreamConfig(name=ATTRIBUTION_STREAM, subjects=ATTRIBUTION_SUBJECTS)
        )
        logger.info("JetStream stream '%s' created", ATTRIBUTION_STREAM)
    except nats.js.errors.BadRequestError as e:
        if "stream name already in use" not in str(e).lower():
            raise
    except Exception as e:
        err = str(e).lower()
        if "already in use" not in err and "stream name already in use" not in err:
            raise


async def ensure_agents_stream() -> None:
    """Garante stream JetStream para jobs de agente."""
    nc = await get_nats()
    js = nc.jetstream()
    try:
        await js.add_stream(StreamConfig(name=AGENTS_STREAM, subjects=AGENTS_SUBJECTS))
        logger.info("JetStream stream '%s' created", AGENTS_STREAM)
    except nats.js.errors.BadRequestError as e:
        if "stream name already in use" not in str(e).lower():
            raise
    except Exception as e:
        err = str(e).lower()
        if "already in use" not in err and "stream name already in use" not in err:
            raise


async def publish(subject: str, payload: dict) -> None:
    if subject.startswith("agents."):
        await ensure_agents_stream()
    else:
        await ensure_attribution_stream()
    nc = await get_nats()
    js = nc.jetstream()
    await js.publish(subject, json.dumps(payload).encode())


async def close_nats() -> None:
    global _nc
    if _nc and _nc.is_connected:
        await _nc.close()
        _nc = None
