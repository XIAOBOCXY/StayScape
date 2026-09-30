from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ..models import HotelService, Merchant, PartnerResource, ProductResource, RoomInventory, TravelProduct


def decimal_text(value) -> str:
    return str(value or 0)


def populate_product_resource_cache(db, resource_cache: dict, products: list[TravelProduct]) -> dict:
    """Batch-load only source resources referenced by a response."""
    hotel_ids = {int(product.hotel_id) for product in products if product.hotel_id is not None}
    for hotel_id in hotel_ids:
        resource_cache[("__hotel_resources__", hotel_id)] = True

    ids = {"PARTNER_RESOURCE": set(), "HOTEL_SERVICE": set(), "ROOM": set()}
    for product in products:
        for row in product.resources or []:
            kind = str(row.resource_type)
            key = (kind, int(row.resource_id))
            if kind in ids and key not in resource_cache:
                ids[kind].add(int(row.resource_id))
        room = getattr(product, "room_inventory", None)
        if room is not None:
            resource_cache[("ROOM", int(room.id))] = room

    if ids["PARTNER_RESOURCE"] and hotel_ids:
        rows = db.scalars(
            select(PartnerResource)
            .options(joinedload(PartnerResource.merchant))
            .join(Merchant, Merchant.id == PartnerResource.merchant_id)
            .where(Merchant.hotel_id.in_(hotel_ids), PartnerResource.id.in_(ids["PARTNER_RESOURCE"]))
        ).all()
        resource_cache.update({("PARTNER_RESOURCE", int(row.id)): row for row in rows})

    if ids["HOTEL_SERVICE"] and hotel_ids:
        rows = db.scalars(
            select(HotelService).where(HotelService.hotel_id.in_(hotel_ids), HotelService.id.in_(ids["HOTEL_SERVICE"]))
        ).all()
        resource_cache.update({("HOTEL_SERVICE", int(row.id)): row for row in rows})

    if ids["ROOM"] and hotel_ids:
        rows = db.scalars(
            select(RoomInventory).where(RoomInventory.hotel_id.in_(hotel_ids), RoomInventory.id.in_(ids["ROOM"]))
        ).all()
        resource_cache.update({("ROOM", int(row.id)): row for row in rows})
    return resource_cache


def build_product_resource_cache(db, products: list[TravelProduct]) -> dict:
    return populate_product_resource_cache(db, {}, products)


def product_to_dict(product: TravelProduct, *, include_adjustments: bool = False, resource_cache: dict | None = None, include_marketing_assets: bool = True) -> dict[str, Any]:
    # A standalone product still resolves each referenced source once. List endpoints
    # pass a shared, targeted resource cache so multiple products reuse the same index.
    if resource_cache is None:
        resource_cache = {}
    data = {
        "id": product.id,
        "hotel_id": product.hotel_id,
        "product_code": product.product_code,
        "product_name": product.product_name,
        "theme": product.theme,
        "version": int(getattr(product, "version", 1) or 1),
        "target_crowd": product.target_crowd,
        "party_size": product.party_size,
        "nights": getattr(product, "nights", 1) or 1,
        "weather": product.weather,
        "target_date": product.target_date,
        "room_inventory_id": product.room_inventory_id,
        "listed_quantity": product.listed_quantity,
        "sale_quantity": product.sale_quantity,
        "unit_cost": product.unit_cost,
        "minimum_allowed_price": product.minimum_allowed_price,
        "suggested_price": product.suggested_price,
        "gross_profit": product.gross_profit,
        "gross_margin": product.gross_margin,
        "minimum_gross_margin_requirement": product.minimum_gross_margin_requirement,
        "visitor_budget_limit": product.visitor_budget_limit,
        "price_anchor": product.price_anchor,
        "bottleneck_resource": product.bottleneck_resource,
        "marketing_title": product.marketing_title,
        "marketing_content": product.marketing_content,
        "marketing_assets": (product.marketing_assets or []) if include_marketing_assets else [],
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
                "available_date": _resource_date(item, resource_cache),
                "start_time": _resource_start(item, resource_cache),
                "end_time": _resource_end(item, resource_cache),
                "address": _resource_address(item, resource_cache),
                "description": _resource_description(item, resource_cache),
                "booking_notice": str(getattr(_resource_object(item, resource_cache), "booking_notice", "") or ""),
                "cancellation_rule": str(getattr(_resource_object(item, resource_cache), "cancellation_rule", "") or ""),
                "image_url": _resource_image_url(item, resource_cache),
                "image_source": _resource_image_source(item, resource_cache),
                "image_attribution": _resource_image_attribution(item, resource_cache),
            }
            for item in product.resources
        ],
        "visitor_copy": dict((getattr(product, "experience_notes", None) or {}).get("visitor_copy") or {}),
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


def _resource_object(item: ProductResource, resource_cache: dict | None = None):
    """Resolve the source object through the product's loaded relationship graph when available."""
    product = item.product
    key = (str(item.resource_type), int(item.resource_id))
    if resource_cache is not None:
        if key in resource_cache:
            return resource_cache[key]
        if item.resource_type == "ROOM" and product and product.room_inventory and product.room_inventory.id == item.resource_id:
            resource_cache[key] = product.room_inventory
            return product.room_inventory
        hotel = product.hotel if product else None
        if hotel:
            marker = ("__hotel_resources__", int(hotel.id))
            if marker not in resource_cache:
                resource_cache[marker] = True
                for service in getattr(hotel, "services", []) or []:
                    resource_cache[("HOTEL_SERVICE", int(service.id))] = service
                for merchant in getattr(hotel, "merchants", []) or []:
                    for resource in getattr(merchant, "resources", []) or []:
                        resource_cache[("PARTNER_RESOURCE", int(resource.id))] = resource
            resource_cache[key] = resource_cache.get(key)
            return resource_cache[key]
        resource_cache[key] = None
        return None
    if item.resource_type == "ROOM" and product and product.room_inventory and product.room_inventory.id == item.resource_id:
        return product.room_inventory
    if product:
        # Product resources intentionally keep only IDs so the deterministic engine
        # owns the source of truth. Lazy loading is safe for the request-scoped DB.
        if item.resource_type == "HOTEL_SERVICE":
            for service in getattr(product.hotel, "services", []) if product.hotel else []:
                if isinstance(service, HotelService) and service.id == item.resource_id:
                    return service
        elif item.resource_type == "PARTNER_RESOURCE":
            for merchant in getattr(product.hotel, "merchants", []) if product.hotel else []:
                for resource in getattr(merchant, "resources", []):
                    if isinstance(resource, PartnerResource) and resource.id == item.resource_id:
                        return resource
    return None


def _resource_date(item: ProductResource, resource_cache: dict | None = None):
    source = _resource_object(item, resource_cache)
    return getattr(source, "available_date", None)


def _resource_start(item: ProductResource, resource_cache: dict | None = None):
    source = _resource_object(item, resource_cache)
    return getattr(source, "start_time", None)


def _resource_end(item: ProductResource, resource_cache: dict | None = None):
    source = _resource_object(item, resource_cache)
    return getattr(source, "end_time", None)


def _resource_address(item: ProductResource, resource_cache: dict | None = None):
    source = _resource_object(item, resource_cache)
    address = str(getattr(source, "address", "") or "").strip()
    if address:
        return address
    product = item.product
    hotel = getattr(product, "hotel", None) if product else None
    if item.resource_type == "PARTNER_RESOURCE" and source is not None:
        merchant = getattr(source, "merchant", None)
        address = str(getattr(merchant, "address", "") or "").strip()
        if address:
            return address
    # Every visitor itinerary has a physical destination. Hotel services and
    # any partner with no saved storefront address fall back to the owning
    # hotel's full address instead of the vague city-only placeholder.
    return str(getattr(hotel, "address", "") or "").strip() or None


def _resource_description(item: ProductResource, resource_cache: dict | None = None):
    source = _resource_object(item, resource_cache)
    return getattr(source, "description", None)


def _resource_image_url(item: ProductResource, resource_cache: dict | None = None) -> str:
    return str(getattr(_resource_object(item, resource_cache), "image_url", "") or "")


def _resource_image_source(item: ProductResource, resource_cache: dict | None = None) -> str:
    return str(getattr(_resource_object(item, resource_cache), "image_source", "") or "")


def _resource_image_attribution(item: ProductResource, resource_cache: dict | None = None) -> str:
    return str(getattr(_resource_object(item, resource_cache), "image_attribution", "") or "")


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
        "image_url": resource.image_url,
        "image_source": resource.image_source,
        "image_attribution": resource.image_attribution,
        "package_enabled": resource.package_enabled,
        "source_type": resource.source_type,
        "status": resource.status,
        "updated_at": resource.updated_at,
        "merchant_name": resource.merchant.merchant_name if resource.merchant else None,
        "referenced_product_count": referenced_product_count,
    }
