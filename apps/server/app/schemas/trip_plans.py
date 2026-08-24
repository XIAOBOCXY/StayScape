from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


TripResourceType = Literal["ROOM", "HOTEL_SERVICE", "PARTNER_RESOURCE"]


class TripPlanRequest(BaseModel):
    """Inputs for the visitor's editable, real-inventory itinerary."""

    natural_language: str = Field(default="", max_length=1200)
    start_date: date
    duration_days: int = Field(default=1, ge=1, le=5)
    target_crowd: str = Field(default="FRIENDS", max_length=60)
    party_size: int = Field(default=2, ge=1, le=8)
    weather: str = Field(default="CLOUDY", max_length=20)
    budget: Decimal | None = Field(default=None, gt=0)
    include_breakfast: bool = True
    plan_name: str = Field(default="我的杭州行程", min_length=1, max_length=180)
    source_product_id: int | None = Field(default=None, ge=1)


class TripPlanItemInput(BaseModel):
    resource_type: TripResourceType
    resource_id: int = Field(ge=1)
    quantity: int = Field(default=1, ge=1, le=20)
    sort_order: int = Field(default=0, ge=0, le=100)


class TripPlanHoldRequest(TripPlanRequest):
    items: list[TripPlanItemInput] = Field(min_length=1, max_length=30)
    contact_name: str = Field(min_length=1, max_length=80)
    contact_phone: str = Field(min_length=6, max_length=40)


class TripPlanUpdateRequest(TripPlanRequest):
    items: list[TripPlanItemInput] = Field(min_length=1, max_length=30)
    contact_name: str | None = Field(default=None, min_length=1, max_length=80)
    contact_phone: str | None = Field(default=None, min_length=6, max_length=40)
