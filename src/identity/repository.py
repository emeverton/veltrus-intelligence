from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.identity.models import IdentityProfile, IdentityProfileMerge, IdentitySignal


async def find_profiles_by_signal_hashes(
    session: AsyncSession,
    hashes: list[str],
) -> list[IdentityProfile]:
    if not hashes:
        return []
    result = await session.execute(
        select(IdentityProfile)
        .join(IdentitySignal)
        .where(IdentitySignal.signal_hash.in_(hashes))
        .distinct()
    )
    return list(result.scalars().all())


async def create_profile(session: AsyncSession) -> IdentityProfile:
    profile = IdentityProfile(id=uuid4())
    session.add(profile)
    await session.flush()
    return profile


async def merge_profiles(
    session: AsyncSession,
    profiles: list[IdentityProfile],
) -> IdentityProfile:
    target = max(profiles, key=lambda p: (p.confidence, -p.created_at.timestamp()))
    sources = [p for p in profiles if p.id != target.id]

    for source in sources:
        await session.execute(
            update(IdentitySignal)
            .where(IdentitySignal.profile_id == source.id)
            .values(profile_id=target.id)
        )
        merge = IdentityProfileMerge(
            source_profile_id=source.id,
            target_profile_id=target.id,
            merge_reason="signal_collision",
        )
        session.add(merge)

    return target


async def upsert_signals(
    session: AsyncSession,
    profile_id: UUID,
    signals: list[dict],
) -> None:
    for s in signals:
        result = await session.execute(
            select(IdentitySignal).where(
                IdentitySignal.signal_type == s["type"].value,
                IdentitySignal.signal_hash == s["hash"],
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.last_seen = datetime.now(timezone.utc)
            existing.profile_id = profile_id
        else:
            signal = IdentitySignal(
                id=uuid4(),
                profile_id=profile_id,
                signal_type=s["type"].value,
                signal_hash=s["hash"],
                confidence=s["confidence"],
                source=s.get("source"),
            )
            session.add(signal)


async def count_signals(session: AsyncSession, profile_id: UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(IdentitySignal).where(
            IdentitySignal.profile_id == profile_id
        )
    )
    return result.scalar_one()


async def get_profile_with_signals(
    session: AsyncSession,
    profile_id: UUID,
) -> tuple[Optional[IdentityProfile], list[IdentitySignal]]:
    profile_result = await session.get(IdentityProfile, profile_id)
    if not profile_result:
        return None, []
    signals_result = await session.execute(
        select(IdentitySignal).where(IdentitySignal.profile_id == profile_id)
    )
    return profile_result, list(signals_result.scalars().all())
