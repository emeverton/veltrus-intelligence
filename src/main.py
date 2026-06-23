import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from src.api.health import router as health_router
from src.api.v1 import agents, attribution, creatives, generate, graphs, identity
from src.agents.worker import run_agent_worker
from src.attribution.worker import run_worker
from src.config import settings
from src.nats_client import close_nats, ensure_agents_stream, ensure_attribution_stream

logger = logging.getLogger(__name__)


async def _run_worker_safe() -> None:
    try:
        await run_worker()
    except Exception:
        logger.exception("Attribution worker crashed")


async def _run_agent_worker_safe() -> None:
    try:
        await run_agent_worker()
    except Exception:
        logger.exception("Agent worker crashed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = None
    agent_worker_task = None
    if settings.attribution_worker_enabled:
        await ensure_attribution_stream()
        await ensure_agents_stream()
        worker_task = asyncio.create_task(_run_worker_safe())
        agent_worker_task = asyncio.create_task(_run_agent_worker_safe())
        logger.info("Attribution NATS worker started")
        logger.info("Agent NATS worker started")
    yield
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    if agent_worker_task:
        agent_worker_task.cancel()
        try:
            await agent_worker_task
        except asyncio.CancelledError:
            pass
    await close_nats()


app = FastAPI(
    title="Veltrus Intelligence API",
    version="0.2.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(identity.router, prefix="/api/v1/identity", tags=["identity"])
app.include_router(attribution.router, prefix="/api/v1/attribution", tags=["attribution"])
app.include_router(graphs.router, prefix="/api/v1/graphs", tags=["graphs"])
app.include_router(creatives.router, prefix="/api/v1/creatives", tags=["creatives"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(generate.router, prefix="/api/v1/generate", tags=["generate"])
