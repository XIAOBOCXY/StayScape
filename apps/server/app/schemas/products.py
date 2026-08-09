from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResourceSelection(BaseModel):
    resource_type: Literal["HOTEL_SERVICE", "PARTNER_RESOURCE"]
    resource_id: int = Field(gt=0)
    quantity_per_package: int = Field(ge=1, le=100)


class GenerateProductRequest(BaseModel):
    target_date: date
    weather: str = "RAIN"
    target_crowd: str = "FAMILY"
    minimum_gross_margin: Decimal = Field(default=Decimal("0.20"), ge=0, lt=1)
    visitor_budget: Decimal = Field(default=Decimal("700"), gt=0)
    theme: str = "雨天亲子非遗"
    room_inventory_id: int | None = Field(default=None, gt=0)
    resource_selections: list[ResourceSelection] = Field(default_factory=list)
    preferred_price: Decimal = Field(default=Decimal("599"), gt=0)
    variant_count: int = Field(default=1, ge=1, le=5)
    creative_direction: str = Field(default="", max_length=160)


class ProductResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_type: str
    resource_id: int
    resource_name: str
    quantity_per_package: int
    unit_cost: Decimal
    replaceable: bool
    required: bool
    available_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    address: str | None = None
    description: str | None = None


class MarketingAsset(BaseModel):
    asset_type: Literal["POSTER", "SOCIAL_POST", "SHORT_VIDEO_SCRIPT", "STORE_CARD"]
    platform: str
    title: str
    content: str
    visual_brief: str = ""
    call_to_action: str = ""
    poster_svg: str = ""


class Financials(BaseModel):
    unit_cost: Decimal
    minimum_allowed_price: Decimal
    suggested_price: Decimal
    gross_profit: Decimal
    gross_margin: Decimal


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    product_code: str
    product_name: str
    theme: str
    target_crowd: str
    weather: str
    target_date: date
    room_inventory_id: int
    sale_quantity: int
    unit_cost: Decimal
    minimum_allowed_price: Decimal
    suggested_price: Decimal
    gross_profit: Decimal
    gross_margin: Decimal
    minimum_gross_margin_requirement: Decimal = Decimal("0.20")
    visitor_budget_limit: Decimal = Decimal("700")
    price_anchor: Decimal = Decimal("599")
    bottleneck_resource: str | None
    marketing_title: str
    marketing_content: str
    marketing_assets: list[MarketingAsset] = Field(default_factory=list)
    recommendation_reason: str
    risk_message: str
    status: str
    created_at: datetime
    updated_at: datetime
    resources: list[ProductResourceRead] = Field(default_factory=list)


class ProductStatusRequest(BaseModel):
    status: Literal["ON_SALE", "PAUSED", "OFF_SHELF"]


class AdjustmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    change_event_id: int | None
    old_quantity: int
    new_quantity: int
    old_price: Decimal
    new_price: Decimal
    action: str
    replacement_resource_id: int | None
    reason: str
    created_at: datetime


class ProductDetailResponse(ProductRead):
    adjustments: list[AdjustmentRead] = Field(default_factory=list)


class ProductGenerateResponse(BaseModel):
    product: ProductRead
    products: list[ProductRead] = Field(default_factory=list)
    trace_id: str
    trace_ids: list[str] = Field(default_factory=list)
    validation: dict[str, Any]
    fallback_used: bool = False


class ProductListResponse(BaseModel):
    items: list[ProductRead]
    total: int


class ProductUpdateRequest(BaseModel):
    target_date: date | None = None
    weather: str | None = None
    target_crowd: str | None = None
    theme: str | None = Field(default=None, min_length=1, max_length=120)
    product_name: str | None = Field(default=None, min_length=1, max_length=180)
    marketing_title: str | None = Field(default=None, min_length=1, max_length=220)
    marketing_content: str | None = None
    recommendation_reason: str | None = None
    risk_message: str | None = None
    room_inventory_id: int | None = Field(default=None, gt=0)
    regenerate_marketing: bool = False


class DynamicAdjustmentRead(BaseModel):
    product_id: int
    product_name: str
    old_quantity: int
    new_quantity: int
    old_price: Decimal
    new_price: Decimal
    action: str
    bottleneck_resource: str | None = None
    status: str
    replacement_resource_id: int | None = None
    reason: str


class ResourceChangeResponse(BaseModel):
    event_id: int
    affected_products: list[DynamicAdjustmentRead]
    message: str
