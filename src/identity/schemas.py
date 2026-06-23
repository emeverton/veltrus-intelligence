from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SignalInput(BaseModel):
    type: str
    value: str


class IngestRequest(BaseModel):
    signals: list[SignalInput]
    source: Optional[str] = None


class ResolveRequest(BaseModel):
    signals: list[SignalInput]
    source: Optional[str] = None


class ProfileResponse(BaseModel):
    profile_id: str
    is_known: bool
    confidence: float
    created_at: datetime
    signals: list[dict]
