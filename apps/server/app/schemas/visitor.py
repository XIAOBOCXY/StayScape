from datetime import date, time
from decimal import Decimal

from pydantic import BaseModel, Field

from .products import ProductRead


class VisitorProductQuery(BaseModel):
    target_date: date | None = None
    target_crowd: str | None = None
    weather: str = "RAIN"
    budget: Decimal | None = Field(default=None, gt=0)
    interest: str | None = None


class VisitorQuestion(BaseModel):
    product_id: int | None = None
    question: str = Field(min_length=1, max_length=500)
    child_age: int | None = Field(default=None, ge=0, le=120)
    weather: str = "RAIN"


class VisitorRecommendRequest(BaseModel):
    target_date: date | None = None
    weather: str = "RAIN"
    adult_count: int = Field(default=2, ge=1, le=20)
    child_count: int = Field(default=1, ge=0, le=20)
    child_ages: list[int] = Field(default_factory=list)
    budget: Decimal = Field(default=Decimal("700"), gt=0)
    interests: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    allergy_information: str = ""
    arrival_time: time | None = None
    preferred_experience_time: time | None = None
    other_requirements: str = ""


class RecommendationResult(BaseModel):
    product: ProductRead
    score: int
    recommendation_reason: str
    budget_match: bool
    children_match: bool
    weather_match: bool
    interest_match: bool
    schedule: list[dict[str, str]]
    limited_adjustments: list[str]
    allergy_warning: str | None = None


class VisitorRecommendResponse(BaseModel):
    results: list[RecommendationResult]
    trace_id: str
    fallback_used: bool = False


class VisitorIntentCreate(BaseModel):
    product_id: int
    adult_count: int = Field(ge=1, le=20)
    child_count: int = Field(ge=0, le=20)
    child_ages: list[int] = Field(default_factory=list)
    budget: Decimal = Field(gt=0)
    interests: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    allergy_information: str = ""
    arrival_time: time | None = None
    preferred_experience_time: time | None = None
    other_requirements: str = ""
    contact_name: str = Field(min_length=1, max_length=80)
    contact_phone: str = Field(min_length=6, max_length=40)

