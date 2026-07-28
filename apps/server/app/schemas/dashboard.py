from decimal import Decimal

from pydantic import BaseModel


class DashboardResponse(BaseModel):
    hotel_id: int
    hotel_name: str
    target_date: str
    room_count: int
    expiring_room_count: int
    available_room_units: int
    partner_resource_count: int
    package_enabled_resource_count: int
    product_count: int
    on_sale_product_count: int
    low_stock_product_count: int
    visitor_intent_count: int
    gross_profit_on_sale: Decimal
    recent_changes: list[dict]

