from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.attribution.models import AttributionConversion, AttributionResult, AttributionTouchpoint


async def ingest_touchpoint(
    session: AsyncSession,
    profile_id: UUID,
    channel: str,
    touchpoint_type: str,
    campaign_id: Optional[str] = None,
    ad_id: Optional[str] = None,
    source: Optional[str] = None,
    medium: Optional[str] = None,
    gclid: Optional[str] = None,
    fbclid: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    metadata: Optional[dict] = None,
) -> AttributionTouchpoint:
    tp = AttributionTouchpoint(
        id=uuid4(),
        profile_id=profile_id,
        channel=channel,
        touchpoint_type=touchpoint_type,
        campaign_id=campaign_id,
        ad_id=ad_id,
        source=source,
        medium=medium,
        gclid=gclid,
        fbclid=fbclid,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        metadata_=metadata or {},
    )
    session.add(tp)
    await session.flush()
    return tp


async def create_conversion(
    session: AsyncSession,
    profile_id: UUID,
    revenue: float,
    currency: str = "BRL",
    metadata: Optional[dict] = None,
) -> AttributionConversion:
    conv = AttributionConversion(
        id=uuid4(),
        profile_id=profile_id,
        revenue=revenue,
        currency=currency,
        metadata_=metadata or {},
    )
    session.add(conv)
    await session.flush()
    return conv


async def get_touchpoints_for_profile(
    session: AsyncSession,
    profile_id: UUID,
    before: Optional[datetime] = None,
) -> list[AttributionTouchpoint]:
    q = select(AttributionTouchpoint).where(AttributionTouchpoint.profile_id == profile_id)
    if before:
        q = q.where(AttributionTouchpoint.occurred_at <= before)
    q = q.order_by(AttributionTouchpoint.occurred_at)
    result = await session.execute(q)
    return list(result.scalars().all())


async def save_results(
    session: AsyncSession,
    conversion_id: UUID,
    profile_id: UUID,
    model: str,
    credits: dict[str, float],
    revenue: float,
) -> None:
    for channel, credit in credits.items():
        result = AttributionResult(
            id=uuid4(),
            conversion_id=conversion_id,
            profile_id=profile_id,
            model=model,
            channel=channel,
            credit=credit,
            revenue_credit=credit * revenue,
        )
        session.add(result)


async def get_results_for_profile(
    session: AsyncSession,
    profile_id: UUID,
    model: Optional[str] = None,
) -> list[AttributionResult]:
    q = select(AttributionResult).where(AttributionResult.profile_id == profile_id)
    if model:
        q = q.where(AttributionResult.model == model)
    result = await session.execute(q)
    return list(result.scalars().all())
