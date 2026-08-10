from typing import Literal

from pydantic import BaseModel, Field


class MarketingAssetOutput(BaseModel):
    asset_type: Literal["POSTER", "SOCIAL_POST", "SHORT_VIDEO_SCRIPT", "STORE_CARD"]
    platform: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=180)
    content: str = Field(default="", max_length=4000)
    visual_brief: str = Field(default="", max_length=500)
    call_to_action: str = Field(default="", max_length=180)
    poster_svg: str = Field(default="", max_length=300000)
    creative_angle: str = Field(default="", max_length=260)
    poster_style: str = Field(default="", max_length=80)


class ProductAgentOutput(BaseModel):
    product_name: str = Field(min_length=1, max_length=180)
    theme: str = Field(min_length=1, max_length=120)
    target_crowd: str = Field(min_length=1, max_length=60)
    room_inventory_id: int = Field(gt=0)
    hotel_service_ids: list[int] = Field(default_factory=list)
    partner_resource_ids: list[int] = Field(default_factory=list)
    resource_quantities: dict[str, int] = Field(default_factory=dict)
    marketing_title: str = Field(min_length=1, max_length=220)
    marketing_content: str = ""
    marketing_assets: list[MarketingAssetOutput] = Field(default_factory=list)
    recommendation_reason: str = ""
    risk_message: str = ""


class VisitorAgentOutput(BaseModel):
    answer: str = ""
    safety_notes: str = ""
    selected_product_ids: list[int] = Field(default_factory=list)
    reasons: dict[str, str] = Field(default_factory=dict)
    schedule_notes: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    limited_adjustments: dict[str, list[str]] = Field(default_factory=dict)
    allergy_warning: str = ""
