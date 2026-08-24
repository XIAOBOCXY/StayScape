from decimal import Decimal

from pydantic import BaseModel


class DashboardSalesPoint(BaseModel):
    date: str
    confirmed_orders: int
    confirmed_revenue: Decimal
    confirmed_gross_profit: Decimal
    on_sale_products: int
    available_packages: int
    listed_value: Decimal


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
    confirmed_order_count: int
    confirmed_revenue: Decimal
    confirmed_gross_profit: Decimal
    held_order_count: int
    held_revenue: Decimal
    available_package_count: int
    listed_value: Decimal
    sales_timeline: list[DashboardSalesPoint]
    recent_changes: list[dict]
