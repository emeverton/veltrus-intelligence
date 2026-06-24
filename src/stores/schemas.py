from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class StoreCreate(BaseModel):
    shop_domain: str
    display_name: Optional[str] = None
    webhook_secret: str
    meta_pixel_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    meta_test_event_code: Optional[str] = None
    google_ads_customer_id: Optional[str] = None
    google_ads_conversion_action: Optional[str] = None


class StoreUpdate(BaseModel):
    display_name: Optional[str] = None
    webhook_secret: Optional[str] = None
    meta_pixel_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    meta_test_event_code: Optional[str] = None
    google_ads_customer_id: Optional[str] = None
    google_ads_conversion_action: Optional[str] = None
    active: Optional[bool] = None


class StoreResponse(BaseModel):
    id: str
    shop_domain: str
    display_name: Optional[str]
    active: bool
    meta_pixel_id: Optional[str]
    google_ads_customer_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
