from fastapi import FastAPI

from src.api.health import router as health_router
from src.api.v1 import agents, attribution, generate, identity
from src.config import settings

app = FastAPI(
    title="Veltrus Intelligence API",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

app.include_router(health_router)
app.include_router(identity.router, prefix="/api/v1/identity", tags=["identity"])
app.include_router(attribution.router, prefix="/api/v1/attribution", tags=["attribution"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(generate.router, prefix="/api/v1/generate", tags=["generate"])
