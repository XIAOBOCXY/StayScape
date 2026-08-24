"""Create a varied public-facing Hangzhou demo pool without automatic image costs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.exceptions import AppError
from .models import HotelService, PartnerResource, RoomInventory, TravelProduct
from .schemas.products import GenerateProductRequest
from .services.product_service import ProductService


# Weather stays an operational compatibility tag; themes lead with the journey.
SHOWCASE_PLANS = [
    {"room": "亲子房", "partner": "室内非遗手作体验", "crowd": "FAMILY", "weather": "RAIN", "theme": "亲子非遗手作周末", "price": "599", "services": [("BREAKFAST", 3), ("LATE_CHECKOUT", 1)], "partner_quantity": 3},
    {"room": "亲子房", "partner": "室内儿童乐园", "crowd": "FAMILY", "weather": "RAIN", "theme": "亲子室内乐园周末", "price": "699", "services": [], "partner_quantity": 1},
    {"room": "家庭套房", "partner": "杭州乐园亲子欢乐体验", "crowd": "FAMILY", "weather": "SUNNY", "theme": "杭州乐园家庭日", "price": "799", "services": [("KIDS_TASK", 1)], "partner_quantity": 1},
    {"room": "亲子联通房", "partner": "儿童剧周末场", "crowd": "FAMILY", "weather": "RAIN", "theme": "家庭儿童剧之夜", "price": "699", "services": [("NIGHT_DESSERT", 1)], "partner_quantity": 1},
    {"room": "湖景大床房", "partner": "城市夜景旅拍", "crowd": "COUPLE", "weather": "SUNNY", "theme": "西湖城市旅拍", "price": "899", "services": [("CITY_MAP", 1)], "partner_quantity": 1},
    {"room": "庭院主题房", "partner": "运河夜游", "crowd": "COUPLE", "weather": "SUNNY", "theme": "运河夜游约会", "price": "799", "services": [("AFTERNOON_TEA", 2)], "partner_quantity": 1},
    {"room": "城市景观房", "partner": "咖啡漫游体验", "crowd": "SOLO", "weather": "CLOUDY", "theme": "一个人的咖啡漫游", "price": "599", "services": [("CITY_MAP", 1)], "partner_quantity": 1},
    {"room": "双床房", "partner": "室内攀岩体验", "crowd": "FRIENDS", "weather": "RAIN", "theme": "城市攀岩运动周末", "price": "699", "services": [("SPORT_SNACK", 1)], "partner_quantity": 1},
    {"room": "影音娱乐房", "partner": "卡丁车周末场", "crowd": "FRIENDS", "weather": "SUNNY", "theme": "卡丁车朋友周末", "price": "799", "services": [("MEDIA_PASS", 1)], "partner_quantity": 1},
    {"room": "大床房", "partner": "杭帮菜双人体验", "crowd": "LOCAL_WEEKEND", "weather": "CLOUDY", "theme": "杭帮菜慢生活周末", "price": "699", "services": [("ROOM_SNACK", 1)], "partner_quantity": 1},
    {"room": "影音娱乐房", "partner": "音乐现场小剧场", "crowd": "COUPLE", "weather": "RAIN", "theme": "城市音乐现场宿", "price": "799", "services": [("CITY_MAP", 1)], "partner_quantity": 1},
    {"room": "城市景观房", "partner": "沉浸式城市演出", "crowd": "LOCAL_WEEKEND", "weather": "CLOUDY", "theme": "杭州城市演出夜", "price": "699", "services": [("CITY_MAP", 1)], "partner_quantity": 1},
    {"room": "双床房", "partner": "良渚文明探索体验", "crowd": "FAMILY", "weather": "CLOUDY", "theme": "良渚文明探索之夜", "price": "699", "services": [("BREAKFAST", 3)], "partner_quantity": 1},
    {"room": "城市景观房", "partner": "城市博物馆主题导览", "crowd": "SOLO", "weather": "RAIN", "theme": "城市博物馆午后", "price": "649", "services": [("CITY_ROUTE", 1)], "partner_quantity": 1},
    {"room": "亲子联通房", "partner": "亲子科学探索实验室", "crowd": "FAMILY", "weather": "RAIN", "theme": "亲子科学探索旅居", "price": "729", "services": [("KIDS_TASK", 1)], "partner_quantity": 1},
    {"room": "大床房", "partner": "南山路看展漫游", "crowd": "COUPLE", "weather": "CLOUDY", "theme": "南山看展慢周末", "price": "699", "services": [("CITY_MAP", 1)], "partner_quantity": 1},
    {"room": "湖景大床房", "partner": "湘湖轻户外探索", "crowd": "SOLO", "weather": "SUNNY", "theme": "湘湖轻户外周末", "price": "679", "services": [("CITY_ROUTE", 1)], "partner_quantity": 1},
    {"room": "双床房", "partner": "钱塘江沿线骑行", "crowd": "FRIENDS", "weather": "SUNNY", "theme": "钱塘江骑行落日", "price": "739", "services": [("SPORT_SNACK", 1)], "partner_quantity": 1},
    {"room": "城市景观房", "partner": "湖滨夜市美食漫游", "crowd": "LOCAL_WEEKEND", "weather": "CLOUDY", "theme": "湖滨夜市美食漫游", "price": "719", "services": [("ROOM_SNACK", 1)], "partner_quantity": 1},
    {"room": "亲子房", "partner": "西溪湿地亲子探索", "crowd": "FAMILY", "weather": "SUNNY", "theme": "西溪亲子发现日", "price": "729", "services": [("KIDS_TASK", 1)], "partner_quantity": 1},
    {"room": "庭院主题房", "partner": "宋韵点茶体验", "crowd": "COUPLE", "weather": "RAIN", "theme": "点茶与庭院慢周末", "price": "699", "services": [("ROOM_TEA_SETUP", 1)], "partner_quantity": 1},
    {"room": "影音娱乐房", "partner": "双人陶艺体验", "crowd": "FRIENDS", "weather": "RAIN", "theme": "双人陶艺夜", "price": "729", "services": [("MEDIA_PASS", 1)], "partner_quantity": 1},
    {"room": "城市景观房", "partner": "青年运动馆体验", "crowd": "LOCAL_WEEKEND", "weather": "CLOUDY", "theme": "周末运动松弛局", "price": "669", "services": [("SPORT_SNACK", 1)], "partner_quantity": 1},
    {"room": "亲子房", "partner": "江南甜品制作", "crowd": "FAMILY", "weather": "RAIN", "theme": "甜品手作亲子下午", "price": "679", "services": [("BREAKFAST", 3)], "partner_quantity": 1},
    {"room": "大床房", "partner": "夜场乐园体验", "crowd": "COUPLE", "weather": "SUNNY", "theme": "乐园夜场双人出发", "price": "759", "services": [("CITY_MAP", 1)], "partner_quantity": 1},
    {"room": "城市景观房", "partner": "西湖晨间城市漫步", "crowd": "SOLO", "weather": "SUNNY", "theme": "西湖晨间慢慢走", "price": "629", "services": [("CITY_ROUTE", 1)], "partner_quantity": 1},
]

LEGACY_THEME_RENAMES = {
    "雨天亲子非遗": "亲子非遗手作周末",
    "雨天室内儿童乐园": "亲子室内乐园周末",
    "雨天攀岩运动宿": "城市攀岩运动周末",
}


def _lookup(db: Session, model, hotel_id: int, field: str, value: str):
    return db.scalar(select(model).where(getattr(model, field) == value, getattr(model, "hotel_id") == hotel_id))


def _normalize_legacy_themes(db: Session, hotel_id: int) -> None:
    for product in db.scalars(select(TravelProduct).where(TravelProduct.hotel_id == hotel_id)):
        replacement = LEGACY_THEME_RENAMES.get(product.theme)
        if not replacement:
            continue
        old = product.theme
        product.theme = replacement
        for field in ("product_name", "marketing_title", "marketing_content", "recommendation_reason", "risk_message"):
            value = getattr(product, field, "") or ""
            setattr(product, field, value.replace(old, replacement))
        if isinstance(product.marketing_assets, list):
            product.marketing_assets = [
                {key: (value.replace(old, replacement) if isinstance(value, str) else value) for key, value in asset.items()}
                for asset in product.marketing_assets
            ]
    db.flush()


def _limit_showcase_products_to_one_booking(
    db: Session, hotel_id: int, target_date: date
) -> None:
    """Keep the optional demo catalogue truthful without claiming large stock."""

    themes = [plan["theme"] for plan in SHOWCASE_PLANS]
    products = db.scalars(
        select(TravelProduct).where(
            TravelProduct.hotel_id == hotel_id,
            TravelProduct.target_date == target_date,
            TravelProduct.theme.in_(themes),
            TravelProduct.status.in_(("ON_SALE", "LOW_STOCK")),
        )
    ).all()
    for product in products:
        product.sale_quantity = 1
        product.status = "ON_SALE"
    db.flush()


def seed_showcase_products(db: Session, hotel_id: int, target_date: date) -> dict[str, int]:
    _normalize_legacy_themes(db, hotel_id)
    _limit_showcase_products_to_one_booking(db, hotel_id, target_date)
    existing_themes = set(db.scalars(select(TravelProduct.theme).where(TravelProduct.hotel_id == hotel_id, TravelProduct.target_date == target_date)))
    created = 0
    service = ProductService(db, hotel_id)
    for plan in SHOWCASE_PLANS:
        if plan["theme"] in existing_themes:
            continue
        room = _lookup(db, RoomInventory, hotel_id, "room_type", plan["room"])
        partner = db.scalar(select(PartnerResource).join(PartnerResource.merchant).where(PartnerResource.resource_name == plan["partner"], PartnerResource.available_date == target_date))
        if not room or not partner:
            continue
        selected = []
        for service_type, quantity in plan["services"]:
            hotel_service = db.scalar(select(HotelService).where(HotelService.hotel_id == hotel_id, HotelService.service_type == service_type, HotelService.available_date == target_date, HotelService.status == "AVAILABLE").order_by(HotelService.id))
            if hotel_service:
                selected.append({"resource_type": "HOTEL_SERVICE", "resource_id": hotel_service.id, "quantity_per_package": quantity})
        selected.append({"resource_type": "PARTNER_RESOURCE", "resource_id": partner.id, "quantity_per_package": plan["partner_quantity"]})
        request = GenerateProductRequest(target_date=target_date, weather=plan["weather"], target_crowd=plan["crowd"], minimum_gross_margin=Decimal("0.20"), visitor_budget=Decimal("1000"), theme=plan["theme"], room_inventory_id=room.id, resource_selections=selected, preferred_price=Decimal(plan["price"]), variant_count=1)
        try:
            with db.begin_nested():
                product, _, _, _ = service.generate(request)
                product.sale_quantity = 1
                product.status = "ON_SALE"
                service.ensure_publish_capacity(product)
                existing_themes.add(plan["theme"])
                created += 1
        except AppError:
            continue
    db.commit()
    return {"showcase_products": len(existing_themes), "created": created}
