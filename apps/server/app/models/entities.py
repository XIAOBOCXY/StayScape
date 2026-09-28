from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
    hotel_id: Mapped[int | None] = mapped_column(ForeignKey("hotels.id"), nullable=True, index=True)

    merchant: Mapped["Merchant | None"] = relationship(back_populates="user", uselist=False)
    hotel: Mapped["Hotel | None"] = relationship(back_populates="users", foreign_keys=[hotel_id])


class AgentApiToken(TimestampMixin, Base):
    """Hash-only read token for external ClawHive/Agent connections."""

    __tablename__ = "agent_api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship()
    hotel: Mapped["Hotel"] = relationship()


class Hotel(TimestampMixin, Base):
    __tablename__ = "hotels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    city: Mapped[str] = mapped_column(String(60), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(80), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    rooms: Mapped[list["RoomInventory"]] = relationship(back_populates="hotel", cascade="all, delete-orphan")
    services: Mapped[list["HotelService"]] = relationship(back_populates="hotel", cascade="all, delete-orphan")
    merchants: Mapped[list["Merchant"]] = relationship(back_populates="hotel", cascade="all, delete-orphan")
    products: Mapped[list["TravelProduct"]] = relationship(back_populates="hotel", cascade="all, delete-orphan")
    users: Mapped[list[User]] = relationship(back_populates="hotel", foreign_keys="User.hotel_id")


class Merchant(TimestampMixin, Base):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)
    merchant_name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(80), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(40), nullable=False)
    cooperation_status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    hotel: Mapped[Hotel] = relationship(back_populates="merchants")
    user: Mapped[User] = relationship(back_populates="merchant")
    resources: Mapped[list["PartnerResource"]] = relationship(back_populates="merchant", cascade="all, delete-orphan")


class RoomInventory(TimestampMixin, Base):
    __tablename__ = "room_inventories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False, index=True)
    room_type: Mapped[str] = mapped_column(String(100), nullable=False)
    available_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    available_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normal_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    minimum_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    accounting_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    max_guests: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    features: Mapped[str] = mapped_column(Text, default="", nullable=False)
    suitable_crowds: Mapped[str] = mapped_column(String(120), default="ALL", nullable=False)
    tags: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    # A merchant-owned upload or a cached, attributed public image.  The UI
    # never needs to hotlink arbitrary travel-site assets directly.
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_source: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    image_attribution: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE", nullable=False)

    hotel: Mapped[Hotel] = relationship(back_populates="rooms")


class HotelService(TimestampMixin, Base):
    __tablename__ = "hotel_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False, index=True)
    service_name: Mapped[str] = mapped_column(String(120), nullable=False)
    service_type: Mapped[str] = mapped_column(String(60), nullable=False)
    available_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reference_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    suitable_crowds: Mapped[str] = mapped_column(String(120), default="ALL", nullable=False)
    replaceable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_source: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    image_attribution: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE", nullable=False)

    hotel: Mapped[Hotel] = relationship(back_populates="services")


class PartnerResource(TimestampMixin, Base):
    __tablename__ = "partner_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), nullable=False, index=True)
    resource_name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    available_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    remaining_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settlement_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    market_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    suitable_crowds: Mapped[str] = mapped_column(String(120), default="ALL", nullable=False)
    minimum_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indoor: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weather_tags: Mapped[str] = mapped_column(String(160), default="RAIN,SUNNY,CLOUDY", nullable=False)
    address: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    booking_notice: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cancellation_rule: Mapped[str] = mapped_column(Text, default="", nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_source: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    image_attribution: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    package_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default="PARTNER", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)

    merchant: Mapped[Merchant] = relationship(back_populates="resources")


class PublicResource(TimestampMixin, Base):
    __tablename__ = "public_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    address: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    opening_hours: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    suitable_crowds: Mapped[str] = mapped_column(String(120), default="ALL", nullable=False)
    weather_tags: Mapped[str] = mapped_column(String(160), default="SUNNY,CLOUDY", nullable=False)
    source: Mapped[str] = mapped_column(String(120), default="official", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)


class TravelKnowledge(TimestampMixin, Base):
    """Reviewed, attributable Hangzhou travel knowledge used as planning context.

    Knowledge records are deliberately separate from ``PartnerResource``.  A
    knowledge entry can help the Agent explain a place or suggest a direction,
    but it is never a sellable resource until a hotel/merchant has supplied a
    real, date-specific PartnerResource with capacity and settlement data.
    """

    __tablename__ = "travel_knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    area: Mapped[str] = mapped_column(String(100), default="杭州", nullable=False)
    address: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    indoor_outdoor: Mapped[str] = mapped_column(String(20), default="MIXED", nullable=False)
    suitable_crowds: Mapped[str] = mapped_column(String(160), default="ALL", nullable=False)
    minimum_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opening_hours: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    weather_adaptations: Mapped[str] = mapped_column(String(180), default="CLOUDY", nullable=False)
    reservation_notice: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ACTIVE: checked within the configured review window; VERIFY_REQUIRED:
    # use only with an explicit confirmation note; STALE: never present as a
    # factual opening-time or reservation claim.
    verification_status: Mapped[str] = mapped_column(String(30), default="VERIFY_REQUIRED", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)


class WeatherSnapshot(TimestampMixin, Base):
    """A cache of a sourced forecast, never a model-invented weather claim."""

    __tablename__ = "weather_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scenario: Mapped[str] = mapped_column(String(20), default="CLOUDY", nullable=False)
    temperature_min: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    temperature_max: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    precipitation_probability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weather_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    advisory: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), default="VERIFY_REQUIRED", nullable=False)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class TravelProduct(TimestampMixin, Base):
    __tablename__ = "travel_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False, index=True)
    product_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    theme: Mapped[str] = mapped_column(String(120), nullable=False)
    target_crowd: Mapped[str] = mapped_column(String(60), nullable=False)
    # A product is sold as one clearly defined group package.  Keeping this on
    # the product (rather than inferring it from the crowd label) makes the
    # breakfast / activity allocation and the hotel-facing wording consistent.
    party_size: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    weather: Mapped[str] = mapped_column(String(20), default="RAIN", nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Merchant-approved upper bound.  ``sale_quantity`` is the live, volatile
    # projection after temporary visitor holds and shared-source allocation.
    # Keeping the two values separate lets a cancelled/expired hold restore
    # the public quantity without silently raising it above what the merchant
    # originally chose to sell.
    listed_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    room_inventory_id: Mapped[int] = mapped_column(ForeignKey("room_inventories.id"), nullable=False)
    sale_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    minimum_allowed_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    suggested_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    gross_profit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    gross_margin: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=Decimal("0"))
    minimum_gross_margin_requirement: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=Decimal("0.20"))
    visitor_budget_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("700"))
    price_anchor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("599"))
    bottleneck_resource: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # The length of stay is part of the product definition: the visitor never
    # re-plans it, and a longer stay must come with real content in between.
    nights: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    marketing_title: Mapped[str] = mapped_column(String(220), default="", nullable=False)
    marketing_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    marketing_assets: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    recommendation_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    risk_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 对话式微调：每次修改都会把版本号 +1，旧版本不被覆盖。
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 体验层调整（例如「第一天下午别排这么满」）存在这里，不影响库存与成本。
    experience_notes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)

    hotel: Mapped[Hotel] = relationship(back_populates="products")
    room_inventory: Mapped[RoomInventory] = relationship()
    resources: Mapped[list["ProductResource"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    visitor_intents: Mapped[list["VisitorIntent"]] = relationship(back_populates="product")
    adjustments: Mapped[list["ProductAdjustmentRecord"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    reviews: Mapped[list["ProductReview"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class AgentConversation(TimestampMixin, Base):
    """One hotel-operating task shared by Web and Feishu entry points."""

    __tablename__ = "agent_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False, index=True)
    source_channel: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(30), nullable=False)
    external_conversation_id: Mapped[str] = mapped_column(String(180), default="", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), default="酒店 AI 运营任务", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    # User/assistant-facing messages only.  Never place model hidden reasoning
    # or credentials here; detailed raw payloads remain in server-only logs.
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    last_execution: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ProductReview(TimestampMixin, Base):
    """A traveller review kept with the product it belongs to.

    Reviews stay in their own table so the visitor page can show real ratings
    and counts instead of a hardcoded score, and so the hotel can see which
    reviews reference which resource.
    """

    __tablename__ = "product_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("travel_products.id"), nullable=False, index=True)
    author_name: Mapped[str] = mapped_column(String(60), nullable=False)
    author_tag: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 1), default=Decimal("5.0"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    highlights: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source: Mapped[str] = mapped_column(String(60), default="平台订单点评", nullable=False)
    stayed_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    product: Mapped["TravelProduct"] = relationship(back_populates="reviews")


class ProductProposal(TimestampMixin, Base):
    """A validated product candidate awaiting an explicit human decision."""

    __tablename__ = "product_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("agent_conversations.id"), nullable=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("travel_products.id"), nullable=False, unique=True, index=True)
    source_channel: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="PENDING_CONFIRMATION", nullable=False, index=True)
    trace_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # These are compact, factual snapshots returned to the hotel operator. They
    # make an Agent recommendation auditable without exposing chain-of-thought.
    insight_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    weather_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    knowledge_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    execution_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    confirmation_action: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    confirmed_by: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProductResource(TimestampMixin, Base):
    __tablename__ = "product_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("travel_products.id"), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_name: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity_per_package: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    replaceable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped[TravelProduct] = relationship(back_populates="resources")


class VisitorIntent(TimestampMixin, Base):
    __tablename__ = "visitor_intents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("travel_products.id"), nullable=False, index=True)
    natural_language: Mapped[str] = mapped_column(Text, default="", nullable=False)
    adult_count: Mapped[int] = mapped_column(Integer, nullable=False)
    child_count: Mapped[int] = mapped_column(Integer, nullable=False)
    child_ages: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    budget: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    interests: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    negative_interests: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    activity_level: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    dietary_restrictions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allergy_information: Mapped[str] = mapped_column(Text, default="", nullable=False)
    arrival_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    preferred_experience_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    other_requirements: Mapped[str] = mapped_column(Text, default="", nullable=False)
    recommendation_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    intent_status: Mapped[str] = mapped_column(String(20), default="NEW", nullable=False)
    reservation_status: Mapped[str] = mapped_column(String(20), default="HELD", nullable=False)
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    allocation_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_name: Mapped[str] = mapped_column(String(80), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(40), nullable=False)

    product: Mapped[TravelProduct] = relationship(back_populates="visitor_intents")


class ResourceChangeEvent(TimestampMixin, Base):
    __tablename__ = "resource_change_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    operator_role: Mapped[str] = mapped_column(String(20), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hotel_id: Mapped[int | None] = mapped_column(ForeignKey("hotels.id"), nullable=True, index=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processing_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ProductAdjustmentRecord(TimestampMixin, Base):
    __tablename__ = "product_adjustment_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("travel_products.id"), nullable=False, index=True)
    change_event_id: Mapped[int | None] = mapped_column(ForeignKey("resource_change_events.id"), nullable=True)
    old_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    new_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    old_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    new_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    replacement_resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)

    product: Mapped[TravelProduct] = relationship(back_populates="adjustments")


class ProductRefinement(TimestampMixin, Base):
    """One natural-language edit applied to a product (kept as an audit trail)."""

    __tablename__ = "product_refinements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotel_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("travel_products.id"), nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    layer: Mapped[str] = mapped_column(String(30), nullable=False, default="CONTENT")
    instruction: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    changes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    checks: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SkillCallLog(TimestampMixin, Base):
    __tablename__ = "skill_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    skill_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    business_scene: Mapped[str] = mapped_column(String(80), nullable=False)
    request_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    raw_response: Mapped[str] = mapped_column(Text, default="", nullable=False)
    final_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    call_status: Mapped[str] = mapped_column(String(20), nullable=False)
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hotel_id: Mapped[int | None] = mapped_column(ForeignKey("hotels.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(20), default="MOCK", nullable=False)
    source_channel: Mapped[str] = mapped_column(String(30), default="SYSTEM", nullable=False)
    actor_role: Mapped[str] = mapped_column(String(30), default="SYSTEM", nullable=False)
    transport: Mapped[str] = mapped_column(String(40), default="mock", nullable=False)
    agent_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    skill_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
