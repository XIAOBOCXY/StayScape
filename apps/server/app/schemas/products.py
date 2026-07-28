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
    bottleneck_resource: str | None
    marketing_title: str
    marketing_content: str
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
    trace_id: str
    validation: dict[str, Any]
    fallback_used: bool = False


class ProductListResponse(BaseModel):
    items: list[ProductRead]
    total: int


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
