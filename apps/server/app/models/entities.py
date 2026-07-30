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

    merchant: Mapped["Merchant | None"] = relationship(back_populates="user", uselist=False)


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
    package_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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


class TravelProduct(TimestampMixin, Base):
    __tablename__ = "travel_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), nullable=False, index=True)
    product_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    theme: Mapped[str] = mapped_column(String(120), nullable=False)
    target_crowd: Mapped[str] = mapped_column(String(60), nullable=False)
    weather: Mapped[str] = mapped_column(String(20), default="RAIN", nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    room_inventory_id: Mapped[int] = mapped_column(ForeignKey("room_inventories.id"), nullable=False)
    sale_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    minimum_allowed_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    suggested_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    gross_profit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    gross_margin: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=Decimal("0"))
    bottleneck_resource: Mapped[str | None] = mapped_column(String(160), nullable=True)
    marketing_title: Mapped[str] = mapped_column(String(220), default="", nullable=False)
    marketing_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    marketing_assets: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    recommendation_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    risk_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)

    hotel: Mapped[Hotel] = relationship(back_populates="products")
    room_inventory: Mapped[RoomInventory] = relationship()
    resources: Mapped[list["ProductResource"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    visitor_intents: Mapped[list["VisitorIntent"]] = relationship(back_populates="product")
    adjustments: Mapped[list["ProductAdjustmentRecord"]] = relationship(back_populates="product", cascade="all, delete-orphan")


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
    adult_count: Mapped[int] = mapped_column(Integer, nullable=False)
    child_count: Mapped[int] = mapped_column(Integer, nullable=False)
    child_ages: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    budget: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    interests: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    dietary_restrictions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allergy_information: Mapped[str] = mapped_column(Text, default="", nullable=False)
    arrival_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    preferred_experience_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    other_requirements: Mapped[str] = mapped_column(Text, default="", nullable=False)
    recommendation_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    intent_status: Mapped[str] = mapped_column(String(20), default="NEW", nullable=False)
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
