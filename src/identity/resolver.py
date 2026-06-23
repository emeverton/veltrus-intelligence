from sqlalchemy.ext.asyncio import AsyncSession

from src.identity import repository as repo
from src.identity.hashing import SIGNAL_CONFIDENCE, SignalType, compute_hash


async def resolve(
    session: AsyncSession,
    signals: list[dict],
    source: str = "api",
) -> dict:
    hashed_signals = []
    for s in signals:
        sig_type = SignalType(s["type"])
        sig_hash = compute_hash(sig_type, s["value"])
        confidence = SIGNAL_CONFIDENCE.get(sig_type, 0.5)
        hashed_signals.append(
            {
                "type": sig_type,
                "hash": sig_hash,
                "confidence": confidence,
                "source": source,
            }
        )

    existing = await repo.find_profiles_by_signal_hashes(
        session,
        [s["hash"] for s in hashed_signals],
    )

    if not existing:
        profile = await repo.create_profile(session)
    elif len(existing) == 1:
        profile = existing[0]
    else:
        profile = await repo.merge_profiles(session, existing)

    await repo.upsert_signals(session, profile.id, hashed_signals)
    await session.commit()
    await session.refresh(profile)

    return {
        "profile_id": str(profile.id),
        "is_known": profile.is_known,
        "confidence": profile.confidence,
        "signals_count": await repo.count_signals(session, profile.id),
    }
