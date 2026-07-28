from pydantic import BaseModel, Field


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
    recommendation_reason: str = ""
    risk_message: str = ""


class VisitorAgentOutput(BaseModel):
    selected_product_ids: list[int] = Field(default_factory=list)
    reasons: dict[str, str] = Field(default_factory=dict)
    schedule_notes: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    limited_adjustments: dict[str, list[str]] = Field(default_factory=dict)
    allergy_warning: str = ""

