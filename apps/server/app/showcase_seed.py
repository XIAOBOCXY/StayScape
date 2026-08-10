"""Create the public-facing multi-persona demo product pool.

These are not hard-coded fake products: every row is generated through the
same ProductService, Mock Agent contract, deterministic cost/margin rules and
publish-capacity guard used by the hotel UI.  The helper only supplies a
repeatable set of operator choices so a fresh demo is immediately presentable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.exceptions import AppError
from .models import HotelService, PartnerResource, RoomInventory, TravelProduct
from .schemas.products import GenerateProductRequest
from .services.product_service import ProductService


SHOWCASE_PLANS = [
    {"room": "亲子房", "partner": "室内非遗手作体验", "crowd": "FAMILY", "weather": "RAIN", "theme": "雨天亲子非遗", "price": "599", "services": [("BREAKFAST", 3), ("LATE_CHECKOUT", 1)], "partner_quantity": 3},
    {"room": "亲子房", "partner": "室内儿童乐园", "crowd": "FAMILY", "weather": "RAIN", "theme": "雨天室内儿童乐园", "price": "699", "services": [], "partner_quantity": 1},
    {"room": "家庭套房", "partner": "杭州乐园亲子欢乐体验", "crowd": "FAMILY", "weather": "SUNNY", "theme": "杭州乐园家庭日", "price": "799", "services": [("KIDS_TASK", 1)], "partner_quantity": 1},
    {"room": "亲子联通房", "partner": "儿童剧周末场", "crowd": "FAMILY", "weather": "RAIN", "theme": "家庭儿童剧之夜", "price": "699", "services": [("NIGHT_DESSERT", 1)], "partner_quantity": 1},
    {"room": "湖景大床房", "partner": "城市夜景旅拍", "crowd": "COUPLE", "weather": "SUNNY", "theme": "西湖城市旅拍", "price": "899", "services": [("CITY_MAP", 1)], "partner_quantity": 1},
    {"room": "庭院主题房", "partner": "运河夜游", "crowd": "COUPLE", "weather": "SUNNY", "theme": "运河夜游约会", "price": "799", "services": [("AFTERNOON_TEA", 2)], "partner_quantity": 1},
    {"room": "城市景观房", "partner": "咖啡漫游体验", "crowd": "SOLO", "weather": "RAIN", "theme": "一个人的咖啡漫游", "price": "599", "services": [("CITY_MAP", 1)], "partner_quantity": 1},
    {"room": "双床房", "partner": "室内攀岩体验", "crowd": "FRIENDS", "weather": "RAIN", "theme": "雨天攀岩运动宿", "price": "699", "services": [("SPORT_SNACK", 1)], "partner_quantity": 1},
    {"room": "影音娱乐房", "partner": "卡丁车周末场", "crowd": "FRIENDS", "weather": "SUNNY", "theme": "卡丁车朋友周末", "price": "799", "services": [("MEDIA_PASS", 1)], "partner_quantity": 1},
    {"room": "大床房", "partner": "杭帮菜双人体验", "crowd": "LOCAL_WEEKEND", "weather": "RAIN", "theme": "杭帮菜慢生活周末", "price": "699", "services": [("ROOM_SNACK", 1)], "partner_quantity": 1},
    {"room": "影音娱乐房", "partner": "音乐现场小剧场", "crowd": "COUPLE", "weather": "RAIN", "theme": "城市音乐现场宿", "price": "799", "services": [("CITY_MAP", 1)], "partner_quantity": 1},
    {"room": "城市景观房", "partner": "沉浸式城市演出", "crowd": "LOCAL_WEEKEND", "weather": "CLOUDY", "theme": "杭州城市演出夜", "price": "699", "services": [("CITY_MAP", 1)], "partner_quantity": 1},
]


def _lookup(db: Session, model, hotel_id: int, field: str, value: str):
    return db.scalar(select(model).where(getattr(model, field) == value, getattr(model, "hotel_id") == hotel_id))


def seed_showcase_products(db: Session, hotel_id: int, target_date: date) -> dict[str, int]:
    current_count = int(db.query(TravelProduct).filter(TravelProduct.hotel_id == hotel_id).count())
    if current_count >= len(SHOWCASE_PLANS):
        return {"showcase_products": current_count, "created": 0}

    created = 0
    service = ProductService(db, hotel_id)
    for plan in SHOWCASE_PLANS:
        room = _lookup(db, RoomInventory, hotel_id, "room_type", plan["room"])
        partner = db.scalar(
            select(PartnerResource)
            .join(PartnerResource.merchant)
            .where(PartnerResource.resource_name == plan["partner"], PartnerResource.available_date == target_date)
        )
        if not room or not partner:
            continue
        selected = []
        for service_type, quantity in plan["services"]:
            hotel_service = db.scalar(select(HotelService).where(HotelService.hotel_id == hotel_id, HotelService.service_type == service_type, HotelService.available_date == target_date, HotelService.status == "AVAILABLE").order_by(HotelService.id))
            if hotel_service:
                selected.append({"resource_type": "HOTEL_SERVICE", "resource_id": hotel_service.id, "quantity_per_package": quantity})
        selected.append({"resource_type": "PARTNER_RESOURCE", "resource_id": partner.id, "quantity_per_package": plan["partner_quantity"]})
        request = GenerateProductRequest(
            target_date=target_date,
            weather=plan["weather"],
            target_crowd=plan["crowd"],
            minimum_gross_margin=Decimal("0.20"),
            visitor_budget=Decimal("1000"),
            theme=plan["theme"],
            room_inventory_id=room.id,
            resource_selections=selected,
            preferred_price=Decimal(plan["price"]),
            variant_count=1,
        )
        try:
            with db.begin_nested():
                product, _, _, _ = service.generate(request)
                product.status = "ON_SALE"
                service.ensure_publish_capacity(product)
                created += 1
        except AppError:
            # A fresh seed should be usable even if an operator has already
            # changed one demo resource.  Leave that candidate out rather than
            # bypassing the same validation used by the real Product Studio.
            continue
    db.commit()
    return {"showcase_products": current_count + created, "created": created}
