from datetime import date, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    room_type: str
    available_date: date
    available_count: int
    normal_price: Decimal
    minimum_price: Decimal
    accounting_cost: Decimal
    max_guests: int
    features: str
    status: str
    updated_at: object


class RoomCreate(BaseModel):
    room_type: str = Field(min_length=1, max_length=100)
    available_date: date
    available_count: int = Field(ge=0)
    normal_price: Decimal = Field(gt=0)
    minimum_price: Decimal = Field(gt=0)
    accounting_cost: Decimal = Field(gt=0)
    max_guests: int = Field(ge=1, le=20)
    features: str = ""


class RoomUpdate(BaseModel):
    room_type: str | None = Field(default=None, min_length=1, max_length=100)
    available_date: date | None = None
    available_count: int | None = Field(default=None, ge=0)
    normal_price: Decimal | None = Field(default=None, gt=0)
    minimum_price: Decimal | None = Field(default=None, gt=0)
    accounting_cost: Decimal | None = Field(default=None, gt=0)
    max_guests: int | None = Field(default=None, ge=1, le=20)
    features: str | None = None
    status: str | None = None
    reason: str = "经营库存调整"


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    service_name: str
    service_type: str
    available_date: date
    available_quantity: int
    unit_cost: Decimal
    reference_price: Decimal
    start_time: time | None
    end_time: time | None
    suitable_crowds: str
    replaceable: bool
    status: str


class ServiceCreate(BaseModel):
    service_name: str = Field(min_length=1, max_length=120)
    service_type: str = "OTHER"
    available_date: date
    available_quantity: int = Field(ge=0)
    unit_cost: Decimal = Field(ge=0)
    reference_price: Decimal = Field(ge=0)
    start_time: time | None = None
    end_time: time | None = None
    suitable_crowds: str = "ALL"
    replaceable: bool = True


class ServiceUpdate(BaseModel):
    available_date: date | None = None
    available_quantity: int | None = Field(default=None, ge=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    reference_price: Decimal | None = Field(default=None, ge=0)
    start_time: time | None = None
    end_time: time | None = None
    status: str | None = None
    reason: str = "酒店服务调整"


class MerchantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    merchant_name: str
    category: str
    contact_name: str
    contact_phone: str
    cooperation_status: str


class PartnerResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_id: int
    resource_name: str
    category: str
    description: str
    available_date: date
    start_time: time | None
    end_time: time | None
    remaining_capacity: int
    settlement_price: Decimal
    market_price: Decimal
    suitable_crowds: str
    minimum_age: int | None
    maximum_age: int | None
    indoor: bool
    weather_tags: str
    address: str
    booking_notice: str
    cancellation_rule: str
    package_enabled: bool
    status: str
    updated_at: object
    merchant_name: str | None = None
    referenced_product_count: int = 0


class PartnerResourceCreate(BaseModel):
    resource_name: str = Field(min_length=1, max_length=160)
    category: str = "CULTURE"
    description: str = ""
    available_date: date
    start_time: time | None = None
    end_time: time | None = None
    remaining_capacity: int = Field(ge=0)
    settlement_price: Decimal = Field(ge=0)
    market_price: Decimal = Field(ge=0)
    suitable_crowds: str = "ALL"
    minimum_age: int | None = Field(default=None, ge=0, le=120)
    maximum_age: int | None = Field(default=None, ge=0, le=120)
    indoor: bool = True
    weather_tags: str = "RAIN,SUNNY,CLOUDY"
    address: str = ""
    booking_notice: str = ""
    cancellation_rule: str = ""
    package_enabled: bool = False

    @field_validator("maximum_age")
    @classmethod
    def age_order(cls, value: int | None, info):
        minimum = info.data.get("minimum_age")
        if value is not None and minimum is not None and value < minimum:
            raise ValueError("maximum_age must be >= minimum_age")
        return value


class PartnerResourceUpdate(BaseModel):
    resource_name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None
    available_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    remaining_capacity: int | None = Field(default=None, ge=0)
    settlement_price: Decimal | None = Field(default=None, ge=0)
    market_price: Decimal | None = Field(default=None, ge=0)
    package_enabled: bool | None = None
    suitable_crowds: str | None = None
    minimum_age: int | None = Field(default=None, ge=0, le=120)
    maximum_age: int | None = Field(default=None, ge=0, le=120)
    indoor: bool | None = None
    weather_tags: str | None = None
    address: str | None = None
    booking_notice: str | None = None
    cancellation_rule: str | None = None
    status: str | None = None
    reason: str = "合作资源更新"


class PackageToggleRequest(BaseModel):
    package_enabled: bool
