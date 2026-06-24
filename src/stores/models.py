from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ShopifyStore(Base):
    __tablename__ = "shopify_stores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_domain: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret: Mapped[str] = mapped_column(Text)
    meta_pixel_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_test_event_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_ads_customer_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_ads_conversion_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
