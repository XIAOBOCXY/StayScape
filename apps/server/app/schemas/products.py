import datetime as dt
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
    # The legacy/default audience is a three-person family; every UI-created
    # request now sends its own explicit group size.
    party_size: int = Field(default=3, ge=1, le=12)
    # How many nights the operator wants to sell; the stay is bound to the
    # product, and extra nights require real content in between.
    nights: int = Field(default=1, ge=1, le=5)
    minimum_gross_margin: Decimal = Field(default=Decimal("0.20"), ge=0, lt=1)
    # None means "no traveller budget was stated"; the room's price floor then
    # decides the price instead of raising a budget error.
    visitor_budget: Decimal | None = Field(default=None, gt=0)
    theme: str = "雨天亲子非遗"
    room_inventory_id: int | None = Field(default=None, gt=0)
    resource_selections: list[ResourceSelection] = Field(default_factory=list)
    preferred_price: Decimal | None = Field(default=None, gt=0)
    variant_count: int = Field(default=1, ge=1, le=5)
    creative_direction: str = Field(default="", max_length=800)


class ProductDraftInterpretRequest(BaseModel):
    natural_language: str = Field(min_length=2, max_length=800)


class ProductDraftInterpretResponse(BaseModel):
    interpreted: dict[str, Any]
    parsed_fields: list[dict[str, Any]] = Field(default_factory=list)
    message: str


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
    image_url: str = ""
    image_source: str = ""
    image_attribution: str = ""


class MarketingAsset(BaseModel):
    asset_type: Literal["POSTER", "SOCIAL_POST", "SHORT_VIDEO_SCRIPT", "STORE_CARD"]
    platform: str
    title: str
    content: str
    visual_brief: str = ""
    call_to_action: str = ""
    poster_svg: str = ""
    creative_angle: str = ""
    poster_style: str = ""
    copy_style: str = ""
    image_url: str = ""
    image_source: str = ""
    image_model: str = ""
    image_watermarked: bool = False
    image_request_id: str = ""


class MarketingRegenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: Literal["ARTISTIC", "PROMOTIONAL", "EMPATHETIC", "SEEDING"] = "SEEDING"
    # A product-detail marketing run is an explicit hotel action, so use the
    # configured server-side Wan model by default rather than returning a
    # template that looks AI-generated but was never actually generated.
    generate_image: bool = True


class BatchMarketingRefinementRequest(BaseModel):
    """A safe bulk creative revision for generated candidates.

    The request intentionally changes only customer-facing content.  It never
    adjusts product resources, capacity, price or publication status, which
    remain subject to the normal product editor and inventory checks.
    """

    model_config = ConfigDict(extra="forbid")

    product_ids: list[int] = Field(min_length=1, max_length=5)
    natural_language: str = Field(min_length=2, max_length=800)
    style: Literal["ARTISTIC", "PROMOTIONAL", "EMPATHETIC", "SEEDING"] = "SEEDING"
    generate_image: bool = False


class Financials(BaseModel):
    unit_cost: Decimal
    minimum_allowed_price: Decimal
    suggested_price: Decimal
    gross_profit: Decimal
    gross_margin: Decimal


class StayOption(BaseModel):
    """One selectable length of stay for a hotel-anchored package."""

    nights: int
    days: int
    label: str
    check_in: date | None = None
    check_out: date | None = None
    price: Decimal = Decimal("0")
    available: bool = True


class StayPlan(StayOption):
    """The stay behind a visitor product: every package includes hotel nights."""

    room_type: str = ""
    room_name: str = ""
    hotel_name: str = ""
    hotel_city: str = ""
    hotel_address: str = ""
    requested_nights: int = 1
    adjusted: bool = False
    max_nights: int = 3
    check_in_time: str = "15:00"
    check_out_time: str = "12:00"
    options: list[StayOption] = Field(default_factory=list)


class DayItem(BaseModel):
    time: str = ""
    title: str
    description: str = ""
    kind: str = ""
    slot: str = "ANY"
    slot_label: str = ""
    duration_minutes: int | None = None
    duration_text: str = ""
    notes: str = ""
    address: str = ""
    included: bool = True
    route_only: bool = False
    area: str = ""
    source_name: str = ""
    source_url: str = ""
    verification_status: str = ""
    opening_hours: str = ""
    reservation_notice: str = ""
    route_role: str = ""


class DayPlan(BaseModel):
    day_index: int
    label: str
    # `date` is the field name users see, so the annotation uses the module
    # alias instead of the imported `date` type that the field would shadow.
    date: dt.date | None = None
    title: str
    summary: str = ""
    slot_summary: str = ""
    items: list[DayItem] = Field(default_factory=list)


class ReviewRead(BaseModel):
    id: int
    author_name: str = "旅人"
    author_tag: str = ""
    rating: Decimal = Decimal("0")
    content: str = ""
    highlights: list[str] = Field(default_factory=list)
    source: str = "平台订单点评"
    stayed_on: date | None = None


class RouteStop(BaseModel):
    time: str = ""
    title: str
    address: str = ""
    kind: str = ""
    slot: str = ""
    included: bool = True
    route_only: bool = False
    source_name: str = ""
    source_url: str = ""
    verification_status: str = ""


class RouteLeg(BaseModel):
    from_stop: str = ""
    to_stop: str = ""
    mode: str = ""
    minutes: int = 0
    note: str = ""
    distance_label: str = ""


class DayRoute(BaseModel):
    day_index: int
    label: str
    # `date` is the field name the UI reads, so the annotation uses the module
    # alias to avoid shadowing the imported `date` type.
    date: dt.date | None = None
    title: str = ""
    summary: str = ""
    stops: list[RouteStop] = Field(default_factory=list)
    legs: list[RouteLeg] = Field(default_factory=list)


class ExperienceDetail(BaseModel):
    name: str
    time: str = ""
    duration: str = ""
    address: str = ""
    included: str = ""
    extra_cost: str = ""
    feature: str = ""
    tips: str = ""
    source_note: str = ""


class DetailSections(BaseModel):
    intro: list[str] = Field(default_factory=list)
    experience_details: list[ExperienceDetail] = Field(default_factory=list)
    spend_notes: list[str] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    product_code: str
    product_name: str
    theme: str
    target_crowd: str
    party_size: int = 2
    nights: int = 1
    weather: str
    target_date: date
    room_inventory_id: int
    listed_quantity: int
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
    # Visitor-facing stay information. Hotel-operated packages are always
    # anchored to at least one room night, so `stay` is never a day trip.
    stay: StayPlan | None = None
    day_plan: list[DayPlan] = Field(default_factory=list)
    route_plan: list[DayRoute] = Field(default_factory=list)
    detail_sections: DetailSections | None = None
    reviews: list[ReviewRead] = Field(default_factory=list)
    rating_average: Decimal | None = None
    rating_count: int = 0
    visitor_copy: dict[str, Any] = Field(default_factory=dict)


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
    provider: str = "MOCK"
    transport: str = "mock"
    agent_id: str = ""
    skill_name: str = "stayscape-product-generator"
    skill_version: str = ""


class ProductDateSummary(BaseModel):
    target_date: date
    sale_quantity: int


class ProductListResponse(BaseModel):
    items: list[ProductRead]
    total: int
    dates: list[ProductDateSummary] = Field(default_factory=list)


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
    # 宣传素材逐条可编辑：按 asset_type 合并到现有素材上，只改文案字段，
    # 不动海报底版以外的真实资源与价格。
    marketing_assets: list[dict[str, Any]] | None = None
    visitor_copy: dict[str, Any] | None = None
    regenerate_marketing: bool = False


class BatchApplyTarget(BaseModel):
    target_date: date
    room_inventory_id: int = Field(gt=0)


class ProductBatchApplyRequest(BaseModel):
    targets: list[BatchApplyTarget] = Field(min_length=1, max_length=20)


class CopyRewriteRequest(BaseModel):
    field: Literal[
        "product_name", "marketing_title", "marketing_content", "recommendation_reason",
        "risk_message", "resource_title", "resource_description", "itinerary_title", "itinerary_description",
        "itinerary_summary", "marketing_asset_title", "marketing_asset_content",
        "detail_text",
    ]
    current_text: str = Field(min_length=1, max_length=3000)
    context: str = Field(default="", max_length=1200)


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


class ProductRefineRequest(BaseModel):
    """对话式微调的一句话指令。"""

    natural_language: str = Field(min_length=1, max_length=500)


class ProductRefineResponse(BaseModel):
    layer: str
    layer_label: str
    version: int
    changes: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    message: str
    product: ProductRead
