from fastapi import APIRouter

from src.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "veltrus-intelligence",
        "version": "0.1.0",
        "debug": settings.debug,
    }
