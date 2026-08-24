from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


_ASSET_TYPE_ALIASES = {
    "POSTER": "POSTER",
    "海报": "POSTER",
    "宣传海报": "POSTER",
    "旅行海报": "POSTER",
    "SOCIAL_POST": "SOCIAL_POST",
    "图文": "SOCIAL_POST",
    "图文笔记": "SOCIAL_POST",
    "小红书": "SOCIAL_POST",
    "小红书笔记": "SOCIAL_POST",
    "社媒文案": "SOCIAL_POST",
    "社交媒体文案": "SOCIAL_POST",
    "公众号推文": "SOCIAL_POST",
    "旅游攻略": "SOCIAL_POST",
    "SHORT_VIDEO_SCRIPT": "SHORT_VIDEO_SCRIPT",
    "短视频": "SHORT_VIDEO_SCRIPT",
    "短视频脚本": "SHORT_VIDEO_SCRIPT",
    "抖音脚本": "SHORT_VIDEO_SCRIPT",
    "视频脚本": "SHORT_VIDEO_SCRIPT",
    "STORE_CARD": "STORE_CARD",
    "商品卡片": "STORE_CARD",
    "产品卡片": "STORE_CARD",
    "店铺卡片": "STORE_CARD",
}


def _plain_text(value: Any) -> Any:
    if isinstance(value, list):
        return "；".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        return "；".join(str(item).strip() for item in value.values() if str(item).strip())
    return value


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

    @field_validator("asset_type", mode="before")
    @classmethod
    def normalize_asset_type(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        compact = value.strip().upper().replace("-", "_").replace(" ", "")
        if compact in _ASSET_TYPE_ALIASES:
            return _ASSET_TYPE_ALIASES[compact]
        raw = value.strip().replace(" ", "")
        if raw in _ASSET_TYPE_ALIASES:
            return _ASSET_TYPE_ALIASES[raw]
        if "海报" in raw:
            return "POSTER"
        if any(token in raw for token in ("视频", "抖音")):
            return "SHORT_VIDEO_SCRIPT"
        if any(token in raw for token in ("图文", "笔记", "推文", "小红书", "社媒", "攻略")):
            return "SOCIAL_POST"
        if "卡片" in raw:
            return "STORE_CARD"
        return value


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
    creative_angle: str = Field(default="", max_length=260)
    poster_style: str = Field(default="", max_length=80)
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

    @field_validator("answer", "safety_notes", "allergy_warning", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: Any) -> Any:
        return _plain_text(value)
