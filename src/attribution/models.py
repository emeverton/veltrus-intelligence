from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class AttributionTouchpoint(Base):
    __tablename__ = "attribution_touchpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_profiles.id", ondelete="CASCADE")
    )
    touchpoint_type: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    campaign_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ad_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    medium: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gclid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fbclid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class AttributionConversion(Base):
    __tablename__ = "attribution_conversions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_profiles.id", ondelete="CASCADE")
    )
    revenue: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(Text, default="BRL")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class AttributionResult(Base):
    __tablename__ = "attribution_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attribution_conversions.id", ondelete="CASCADE")
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_profiles.id")
    )
    model: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    campaign_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credit: Mapped[float] = mapped_column(Float)
    revenue_credit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
