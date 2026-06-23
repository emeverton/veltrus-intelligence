from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.attribution import repository as repo
from src.attribution.models_math import Touchpoint, run_all_sync_models
from src.attribution.schemas import (
    AttributionReportResponse,
    ComputeRequest,
    ComputeResponse,
    TouchpointIngestRequest,
)
from src.database import get_session
from src.nats_client import publish

router = APIRouter()

SHAPLEY_SUBJECT = "attribution.shapley.compute"


@router.post("/touchpoint")
async def ingest_touchpoint(
    payload: TouchpointIngestRequest,
    session: AsyncSession = Depends(get_session),
):
    tp = await repo.ingest_touchpoint(
        session,
        profile_id=payload.profile_id,
        channel=payload.channel,
        touchpoint_type=payload.touchpoint_type,
        campaign_id=payload.campaign_id,
        source=payload.source,
        medium=payload.medium,
        gclid=payload.gclid,
        fbclid=payload.fbclid,
        occurred_at=payload.occurred_at,
        metadata=payload.metadata or {},
    )
    await session.commit()
    return {"touchpoint_id": str(tp.id), "profile_id": str(payload.profile_id)}


@router.post("/compute", response_model=ComputeResponse)
async def compute_attribution(
    payload: ComputeRequest,
    session: AsyncSession = Depends(get_session),
):
    conversion_time = payload.occurred_at or datetime.now(timezone.utc)

    conversion = await repo.create_conversion(
        session,
        profile_id=payload.profile_id,
        revenue=payload.revenue,
        currency=payload.currency,
        metadata=payload.metadata or {},
    )

    touchpoints_db = await repo.get_touchpoints_for_profile(
        session, payload.profile_id, before=conversion_time
    )

    if not touchpoints_db:
        await session.commit()
        return ComputeResponse(
            conversion_id=str(conversion.id),
            profile_id=str(payload.profile_id),
            revenue=payload.revenue,
            results={},
            shapley_job_id=None,
            message="No touchpoints found before conversion — zero-touch conversion recorded",
        )

    tp_list = [
        Touchpoint(
            channel=t.channel,
            campaign_id=t.campaign_id,
            occurred_at=t.occurred_at,
        )
        for t in touchpoints_db
    ]

    sync_results = run_all_sync_models(tp_list, conversion_time)

    for model_name, credits in sync_results.items():
        await repo.save_results(
            session, conversion.id, payload.profile_id, model_name, credits, payload.revenue
        )

    await session.commit()

    await publish(
        SHAPLEY_SUBJECT,
        {
            "conversion_id": str(conversion.id),
            "profile_id": str(payload.profile_id),
            "revenue": payload.revenue,
        },
    )

    return ComputeResponse(
        conversion_id=str(conversion.id),
        profile_id=str(payload.profile_id),
        revenue=payload.revenue,
        results=sync_results,
        shapley_job_id=str(conversion.id),
        message="Sync models computed. Shapley queued — check /report for results.",
    )


@router.get("/report/{profile_id}", response_model=AttributionReportResponse)
async def get_attribution_report(
    profile_id: UUID,
    model: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    results = await repo.get_results_for_profile(session, profile_id, model=model)
    if not results:
        raise HTTPException(status_code=404, detail="No attribution results found for profile")

    by_model: dict[str, dict] = {}
    for r in results:
        if r.model not in by_model:
            by_model[r.model] = {}
        by_model[r.model][r.channel] = {
            "credit": round(r.credit, 4),
            "revenue_credit": round(r.revenue_credit or 0, 2),
        }

    return AttributionReportResponse(
        profile_id=str(profile_id),
        models=by_model,
        total_results=len(results),
    )
