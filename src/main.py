import asyncio
from contextlib import asynccontextmanager
import logging

import sentry_sdk
from fastapi import FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from src.api.health import router as health_router
from src.api.v1 import (
    admin,
    agents,
    analytics,
    attribution,
    creatives,
    generate,
    graphs,
    identity,
    integrations,
    webhooks,
)
from src.agents.worker import run_agent_worker
from src.attribution.worker import run_worker
from src.config import settings
from src.nats_client import close_nats, ensure_agents_stream, ensure_attribution_stream

logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(transaction_style="url"),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1,
        environment="production",
        release="veltrus-intelligence@0.8.0",
        send_default_pii=False,
    )


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
    version="0.8.0",
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
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(
    integrations.router, prefix="/api/v1/integrations", tags=["integrations"]
)
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
