from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.identity.repository import get_profile_with_signals
from src.identity.resolver import resolve
from src.identity.schemas import IngestRequest, ProfileResponse, ResolveRequest

router = APIRouter()


@router.post("/ingest")
async def ingest_signals(
    payload: IngestRequest,
    session: AsyncSession = Depends(get_session),
):
    """Recebe sinais brutos e retorna o profile resolvido."""
    signals = [{"type": s.type, "value": s.value} for s in payload.signals]
    return await resolve(session, signals, source=payload.source or "api")


@router.post("/resolve")
async def resolve_identity(
    payload: ResolveRequest,
    session: AsyncSession = Depends(get_session),
):
    """Alias de /ingest com output compatível SaaS."""
    signals = [{"type": s.type, "value": s.value} for s in payload.signals]
    return await resolve(session, signals, source=payload.source or "api")


@router.get("/profile/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    profile, signals = await get_profile_with_signals(session, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileResponse(
        profile_id=str(profile.id),
        is_known=profile.is_known,
        confidence=profile.confidence,
        created_at=profile.created_at,
        signals=[
            {"type": s.signal_type, "confidence": s.confidence, "source": s.source}
            for s in signals
        ],
    )
