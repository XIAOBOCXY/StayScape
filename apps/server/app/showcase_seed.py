"""Create a varied public-facing Hangzhou demo pool without automatic image costs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import HotelService, PartnerResource, ProductResource, RoomInventory, TravelProduct
from .services.inventory_service import reconcile_published_capacity
from .services.poster_service import poster_asset


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


def _copy_for(plan: dict[str, object], partner: PartnerResource, target_date: date) -> tuple[str, str, str]:
    """Visitor-facing demo words, without pretending an internal rule is copy."""
    name = str(plan["theme"])
    date_label = f"{target_date.month} 月 {target_date.day} 日"
    title = f"{name} · 杭州一晚"
    content = (
        f"{date_label}，先把行李放进房间，再去 {partner.address or '杭州城里'} 体验 {partner.resource_name}。"
        "不用把一天排满，给散步、吃饭和临时发现留一点空白。"
    )
    reason = f"适合想把 {partner.resource_name} 排进杭州行程、又希望晚上住得舒服一点的你。"
    return title, content, reason


def _direct_assets(title: str, content: str, partner: PartnerResource, room: RoomInventory, plan: dict[str, object], target_date: date, price: Decimal, index: int) -> list[dict[str, str]]:
    poster = poster_asset(
        title=title,
        content=content,
        partner_name=partner.resource_name,
        room_name=room.room_type,
        address=partner.address,
        price=str(price),
        target_crowd=str(plan["crowd"]),
        theme=str(plan["theme"]),
        weather=str(plan["weather"]),
        target_date=target_date.isoformat(),
        variant_index=index,
        creative_angle="真实时间线与体验地点的旅行记录感",
    )
    return [
        {
            "asset_type": "POSTER",
            "platform": "旅行分享海报",
            "title": title,
            "content": content,
            "visual_brief": "按路线和具体体验呈现，预留分享文字空间",
            "call_to_action": "",
            "copy_style": "SEEDING",
            **poster,
        },
        {
            "asset_type": "SOCIAL_POST",
            "platform": "小红书 / 抖音图文",
            "title": f"{partner.resource_name} 这段安排很对味",
            "content": f"这次没有赶着刷景点，住下以后去了一趟 {partner.resource_name}。\n{partner.description}\n如果你也想把杭州过得松一点，可以把这一段留在行程里。",
            "visual_brief": "像旅行者回顾周末的三张照片，不写硬广口号",
            "call_to_action": "",
            "copy_style": "SEEDING",
        },
        {
            "asset_type": "SHORT_VIDEO_SCRIPT",
            "platform": "短视频",
            "title": "杭州周末的三个镜头",
            "content": f"镜头一：抵达 {room.room_type} 放下行李。\n镜头二：前往 {partner.resource_name}，拍下开始前的细节。\n镜头三：回到杭州的夜色里，记录今天最想留住的一瞬间。",
            "visual_brief": "竖版、自然光、真实旅行记录",
            "call_to_action": "",
            "copy_style": "ARTISTIC",
        },
    ]


def seed_showcase_products(db: Session, hotel_id: int, target_date: date) -> dict[str, int]:
    """Seed a small, diverse merchant-approved product pool per date.

    It never calls a model at startup and it does not artificially set every
    product to one unit.  The rest of the resource pool remains available for
    operator-created products and visitor custom itineraries.
    """
    _normalize_legacy_themes(db, hotel_id)
    existing_themes = set(
        db.scalars(
            select(TravelProduct.theme).where(
                TravelProduct.hotel_id == hotel_id,
                TravelProduct.target_date == target_date,
            )
        )
    )
    start = target_date.toordinal() % len(SHOWCASE_PLANS)
    plans = [SHOWCASE_PLANS[(start + offset * 7) % len(SHOWCASE_PLANS)] for offset in range(3)]
    created = 0
    for index, plan in enumerate(plans):
        if plan["theme"] in existing_themes:
            continue
        room = db.scalar(
            select(RoomInventory).where(
                RoomInventory.hotel_id == hotel_id,
                RoomInventory.room_type == plan["room"],
                RoomInventory.available_date == target_date,
                RoomInventory.status == "AVAILABLE",
                RoomInventory.available_count > 0,
            )
        )
        partner = db.scalar(
            select(PartnerResource)
            .join(PartnerResource.merchant)
            .where(
                PartnerResource.resource_name == plan["partner"],
                PartnerResource.available_date == target_date,
                PartnerResource.package_enabled.is_(True),
                PartnerResource.status == "AVAILABLE",
            )
        )
        if not room or not partner:
            continue
        rows = [
            ProductResource(
                resource_type="ROOM",
                resource_id=room.id,
                resource_name=room.room_type,
                quantity_per_package=1,
                unit_cost=room.accounting_cost,
                replaceable=False,
                required=True,
            ),
            ProductResource(
                resource_type="PARTNER_RESOURCE",
                resource_id=partner.id,
                resource_name=partner.resource_name,
                quantity_per_package=int(plan["partner_quantity"]),
                unit_cost=partner.settlement_price,
                replaceable=True,
                required=True,
            ),
        ]
        unit_cost = Decimal(room.accounting_cost) + Decimal(partner.settlement_price) * int(plan["partner_quantity"])
        capacity = min(room.available_count, partner.remaining_capacity // max(1, int(plan["partner_quantity"])))
        for service_type, quantity in plan["services"]:
            service = db.scalar(
                select(HotelService).where(
                    HotelService.hotel_id == hotel_id,
                    HotelService.service_type == service_type,
                    HotelService.available_date == target_date,
                    HotelService.status == "AVAILABLE",
                    HotelService.available_quantity >= quantity,
                ).order_by(HotelService.id)
            )
            if not service:
                continue
            rows.append(
                ProductResource(
                    resource_type="HOTEL_SERVICE",
                    resource_id=service.id,
                    resource_name=service.service_name,
                    quantity_per_package=quantity,
                    unit_cost=service.unit_cost,
                    replaceable=service.replaceable,
                    required=True,
                )
            )
            unit_cost += Decimal(service.unit_cost) * quantity
            capacity = min(capacity, service.available_quantity // max(1, quantity))
        price = max(Decimal(str(plan["price"])), (unit_cost * Decimal("1.22")).quantize(Decimal("0.01")))
        minimum_price = (unit_cost * Decimal("1.20")).quantize(Decimal("0.01"))
        quantity = max(1, min(3, capacity))
        title, content, reason = _copy_for(plan, partner, target_date)
        product = TravelProduct(
            hotel_id=hotel_id,
            product_code=f"SC-{target_date.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}",
            product_name=title,
            theme=str(plan["theme"]),
            target_crowd=str(plan["crowd"]),
            weather=str(plan["weather"]),
            target_date=target_date,
            room_inventory_id=room.id,
            listed_quantity=quantity,
            sale_quantity=quantity,
            unit_cost=unit_cost,
            minimum_allowed_price=minimum_price,
            suggested_price=price,
            gross_profit=(price - unit_cost).quantize(Decimal("0.01")),
            gross_margin=((price - unit_cost) / price).quantize(Decimal("0.000001")),
            minimum_gross_margin_requirement=Decimal("0.20"),
            visitor_budget_limit=max(price + Decimal("200"), Decimal("900")),
            price_anchor=price,
            bottleneck_resource=partner.resource_name if partner.remaining_capacity <= room.available_count else room.room_type,
            marketing_title=title,
            marketing_content=content,
            marketing_assets=_direct_assets(title, content, partner, room, plan, target_date, price, index),
            recommendation_reason=reason,
            risk_message="这组日期的可预约名额不多，确认前会再次为你核对。" if quantity <= 2 else "",
            status="LOW_STOCK" if quantity <= 2 else "ON_SALE",
            resources=rows,
        )
        db.add(product)
        existing_themes.add(str(plan["theme"]))
        created += 1
    db.flush()
    reconcile_published_capacity(db, hotel_id)
    db.commit()
    return {"showcase_products": len(existing_themes), "created": created}
