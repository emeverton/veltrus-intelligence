from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TouchpointIngestRequest(BaseModel):
    profile_id: UUID
    channel: str
    touchpoint_type: str
    campaign_id: Optional[str] = None
    source: Optional[str] = None
    medium: Optional[str] = None
    gclid: Optional[str] = None
    fbclid: Optional[str] = None
    occurred_at: Optional[datetime] = None
    metadata: Optional[dict] = None


class ComputeRequest(BaseModel):
    profile_id: UUID
    revenue: float
    currency: str = "BRL"
    occurred_at: Optional[datetime] = None
    metadata: Optional[dict] = None


class ComputeResponse(BaseModel):
    conversion_id: str
    profile_id: str
    revenue: float
    results: dict
    shapley_job_id: Optional[str]
    message: str


class AttributionReportResponse(BaseModel):
    profile_id: str
    models: dict
    total_results: int
