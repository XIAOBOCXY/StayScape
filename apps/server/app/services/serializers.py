from typing import Any

from ..models import HotelService, PartnerResource, ProductResource, RoomInventory, TravelProduct


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
        "marketing_assets": product.marketing_assets or [],
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
                "available_date": _resource_date(item),
                "start_time": _resource_start(item),
                "end_time": _resource_end(item),
                "address": _resource_address(item),
                "description": _resource_description(item),
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


def _resource_object(item: ProductResource):
    """Resolve the source object through the product's loaded relationship graph when available."""
    product = item.product
    if item.resource_type == "ROOM" and product and product.room_inventory and product.room_inventory.id == item.resource_id:
        return product.room_inventory
    if product:
        # Product resources intentionally keep only IDs so the deterministic engine
        # owns the source of truth. Lazy loading is safe for the request-scoped DB.
        for service in getattr(product.hotel, "services", []) if product.hotel else []:
            if isinstance(service, HotelService) and service.id == item.resource_id:
                return service
        for merchant in getattr(product.hotel, "merchants", []) if product.hotel else []:
            for resource in getattr(merchant, "resources", []):
                if isinstance(resource, PartnerResource) and resource.id == item.resource_id:
                    return resource
    return None


def _resource_date(item: ProductResource):
    source = _resource_object(item)
    return getattr(source, "available_date", None)


def _resource_start(item: ProductResource):
    source = _resource_object(item)
    return getattr(source, "start_time", None)


def _resource_end(item: ProductResource):
    source = _resource_object(item)
    return getattr(source, "end_time", None)


def _resource_address(item: ProductResource):
    source = _resource_object(item)
    return getattr(source, "address", None)


def _resource_description(item: ProductResource):
    source = _resource_object(item)
    return getattr(source, "description", None)


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
