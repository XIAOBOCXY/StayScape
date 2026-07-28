from typing import Any

from ..models import PartnerResource, TravelProduct


def decimal_text(value) -> str:
    return str(value or 0)


def product_to_dict(product: TravelProduct, *, include_adjustments: bool = False) -> dict[str, Any]:
    data = {
        "id": product.id,
        "hotel_id": product.hotel_id,
        "product_code": product.product_code,
        "product_name": product.product_name,
        "theme": product.theme,
        "target_crowd": product.target_crowd,
        "weather": product.weather,
        "target_date": product.target_date,
        "room_inventory_id": product.room_inventory_id,
        "sale_quantity": product.sale_quantity,
        "unit_cost": product.unit_cost,
        "minimum_allowed_price": product.minimum_allowed_price,
        "suggested_price": product.suggested_price,
        "gross_profit": product.gross_profit,
        "gross_margin": product.gross_margin,
        "bottleneck_resource": product.bottleneck_resource,
        "marketing_title": product.marketing_title,
        "marketing_content": product.marketing_content,
        "recommendation_reason": product.recommendation_reason,
        "risk_message": product.risk_message,
        "status": product.status,
        "created_at": product.created_at,
        "updated_at": product.updated_at,
        "resources": [
            {
                "id": item.id,
                "resource_type": item.resource_type,
                "resource_id": item.resource_id,
                "resource_name": item.resource_name,
                "quantity_per_package": item.quantity_per_package,
                "unit_cost": item.unit_cost,
                "replaceable": item.replaceable,
                "required": item.required,
            }
            for item in product.resources
        ],
    }
    if include_adjustments:
        data["adjustments"] = [
            {
                "id": item.id,
                "product_id": item.product_id,
                "change_event_id": item.change_event_id,
                "old_quantity": item.old_quantity,
                "new_quantity": item.new_quantity,
                "old_price": item.old_price,
                "new_price": item.new_price,
                "action": item.action,
                "replacement_resource_id": item.replacement_resource_id,
                "reason": item.reason,
                "created_at": item.created_at,
            }
            for item in product.adjustments
        ]
    return data


def partner_resource_to_dict(resource: PartnerResource, referenced_product_count: int = 0) -> dict[str, Any]:
    return {
        "id": resource.id,
        "merchant_id": resource.merchant_id,
        "resource_name": resource.resource_name,
        "category": resource.category,
        "description": resource.description,
        "available_date": resource.available_date,
        "start_time": resource.start_time,
        "end_time": resource.end_time,
        "remaining_capacity": resource.remaining_capacity,
        "settlement_price": resource.settlement_price,
        "market_price": resource.market_price,
        "suitable_crowds": resource.suitable_crowds,
        "minimum_age": resource.minimum_age,
        "maximum_age": resource.maximum_age,
        "indoor": resource.indoor,
        "weather_tags": resource.weather_tags,
        "address": resource.address,
        "booking_notice": resource.booking_notice,
        "cancellation_rule": resource.cancellation_rule,
        "package_enabled": resource.package_enabled,
        "status": resource.status,
        "updated_at": resource.updated_at,
        "merchant_name": resource.merchant.merchant_name if resource.merchant else None,
        "referenced_product_count": referenced_product_count,
    }
