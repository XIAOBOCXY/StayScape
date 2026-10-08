"""Create a varied public-facing Hangzhou demo pool without pretending to run AI."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_UP
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import HotelService, Merchant, PartnerResource, ProductResource, RoomInventory, TravelProduct, VisitorIntent
from .schemas.products import GenerateProductRequest
from .services.inventory_service import reconcile_published_capacity
from .services.product_service import ProductService


# Weather stays an operational compatibility tag; themes lead with the journey.
SHOWCASE_PLANS = [
    {"room": "亲子房", "partner": "室内非遗手作体验", "crowd": "FAMILY", "weather": "RAIN", "theme": "亲子非遗手作周末", "price": "599", "services": [("BREAKFAST", 3), ("LATE_CHECKOUT", 1)], "partner_quantity": 3},
    {"room": "亲子房", "partner": "室内儿童乐园", "crowd": "FAMILY", "weather": "RAIN", "theme": "亲子室内乐园周末", "price": "699", "services": [], "partner_quantity": 1},
    {"room": "家庭套房", "partner": "主题乐园家庭日票", "crowd": "FAMILY", "weather": "SUNNY", "theme": "主题乐园亲子畅玩", "price": "799", "services": [("KIDS_TASK", 1)], "partner_quantity": 1},
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


def refresh_showcase_itineraries(
    db: Session,
    hotel_id: int,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, int]:
    """Rebuild unbooked future SC products with the live day-balanced selector.

    Historical products and any product referenced by a visitor order are left
    untouched. The selector keeps exact, date-specific partner sessions and
    validates crowd size, remaining capacity, full session duration, overlaps,
    transfer buffers, meal slots and all-day activities.
    """
    first_day = max(start_date or date.today(), date.today())
    query = (
        select(TravelProduct)
        .options(selectinload(TravelProduct.resources))
        .where(
            TravelProduct.hotel_id == hotel_id,
            TravelProduct.product_code.like("SC-%"),
            TravelProduct.target_date >= first_day,
            TravelProduct.status.in_({"ON_SALE", "LOW_STOCK", "SOLD_OUT"}),
        )
        .order_by(TravelProduct.target_date, TravelProduct.id)
    )
    if end_date:
        query = query.where(TravelProduct.target_date <= end_date)
    products = list(db.scalars(query).unique().all())
    if not products:
        return {"updated": 0, "skipped_with_orders": 0, "skipped_without_stay": 0, "skipped_without_experiences": 0}

    product_ids = [item.id for item in products]
    booked_ids = set(db.scalars(
        select(VisitorIntent.product_id).where(VisitorIntent.product_id.in_(product_ids)).distinct()
    ).all())
    rooms_by_id = {
        item.id: item
        for item in db.scalars(select(RoomInventory).where(RoomInventory.hotel_id == hotel_id)).all()
    }
    partner_ids = {
        row.resource_id
        for product in products
        for row in product.resources
        if row.resource_type == "PARTNER_RESOURCE"
    }
    partners_by_id = {
        item.id: item
        for item in db.scalars(
            select(PartnerResource)
            .join(PartnerResource.merchant)
            .options(selectinload(PartnerResource.merchant))
            .where(PartnerResource.id.in_(partner_ids), Merchant.hotel_id == hotel_id)
        ).unique().all()
    } if partner_ids else {}
    service = ProductService(db, hotel_id)
    refreshed = 0
    skipped_with_orders = 0
    skipped_without_stay = 0
    skipped_without_experiences = 0

    for product in products:
        if product.id in booked_ids:
            skipped_with_orders += 1
            continue
        nights = max(1, int(product.nights or 1))
        room = rooms_by_id.get(int(product.room_inventory_id or 0))
        if not room or room.available_date != product.target_date or room.status != "AVAILABLE":
            skipped_without_stay += 1
            continue
        night_dates = [product.target_date + timedelta(days=offset) for offset in range(nights)]
        stay_rooms = list(db.scalars(
            select(RoomInventory).where(
                RoomInventory.hotel_id == hotel_id,
                RoomInventory.room_type == room.room_type,
                RoomInventory.available_date.in_(night_dates),
                RoomInventory.status == "AVAILABLE",
                RoomInventory.available_count > 0,
            ).order_by(RoomInventory.available_date)
        ).all())
        room_by_date = {item.available_date: item for item in stay_rooms}
        if any(day not in room_by_date for day in night_dates):
            skipped_without_stay += 1
            continue

        party_size = max(1, int(product.party_size or 2))
        request = GenerateProductRequest(
            target_date=product.target_date,
            weather=str(product.weather or "CLOUDY"),
            target_crowd=str(product.target_crowd or "COUPLE"),
            party_size=party_size,
            nights=nights,
            minimum_gross_margin=Decimal(str(product.minimum_gross_margin_requirement or "0.20")),
            theme=str(product.theme or "杭州城市体验"),
            room_inventory_id=room.id,
            variant_count=3,
        )

        services = list(db.scalars(select(HotelService).where(
            HotelService.hotel_id == hotel_id,
            HotelService.available_date == product.target_date,
            HotelService.status == "AVAILABLE",
        ).order_by(HotelService.id)).all())
        services_by_id = {item.id: item for item in services}
        base_selections: list[dict[str, int | str]] = []
        retained_services: set[int] = set()
        for row in product.resources:
            if row.resource_type != "HOTEL_SERVICE":
                continue
            existing_service = services_by_id.get(int(row.resource_id))
            quantity = max(1, int(row.quantity_per_package or 1))
            if existing_service and existing_service.available_quantity >= quantity:
                base_selections.append({"resource_type": "HOTEL_SERVICE", "resource_id": existing_service.id, "quantity_per_package": quantity})
                retained_services.add(existing_service.id)
        for service_type, quantity in (("BREAKFAST", party_size), ("LATE_CHECKOUT", 1)):
            if any(services_by_id[item_id].service_type == service_type for item_id in retained_services):
                continue
            candidate = next((item for item in services if item.service_type == service_type and item.available_quantity >= quantity), None)
            if candidate:
                base_selections.append({"resource_type": "HOTEL_SERVICE", "resource_id": candidate.id, "quantity_per_package": quantity})
                retained_services.add(candidate.id)

        anchor_id = None
        for row in product.resources:
            if row.resource_type != "PARTNER_RESOURCE":
                continue
            candidate = partners_by_id.get(int(row.resource_id))
            if candidate and candidate.available_date == product.target_date and candidate.start_time and candidate.end_time and service._partner_candidate(candidate, request):
                anchor_id = candidate.id
                base_selections.append({"resource_type": "PARTNER_RESOURCE", "resource_id": candidate.id, "quantity_per_package": party_size})
                break

        selections = service._default_selections(
            request,
            room,
            variant_index=product.id % 5,
            base_selections=base_selections,
        )
        selected_partner_ids = {
            int(item["resource_id"])
            for item in selections
            if item["resource_type"] == "PARTNER_RESOURCE"
        }
        selected_service_ids = {
            int(item["resource_id"])
            for item in selections
            if item["resource_type"] == "HOTEL_SERVICE"
        }
        # Resolve both the preserved anchor and all newly selected sessions in
        # one bounded query; only the former was necessarily in partners_by_id.
        selected_partners = list(db.scalars(
            select(PartnerResource)
            .join(PartnerResource.merchant)
            .options(selectinload(PartnerResource.merchant))
            .where(PartnerResource.id.in_(selected_partner_ids), Merchant.hotel_id == hotel_id)
        ).unique().all()) if selected_partner_ids else []
        if not selected_partners:
            skipped_without_experiences += 1
            continue
        selected_service_rows = list(db.scalars(select(HotelService).where(
            HotelService.hotel_id == hotel_id,
            HotelService.id.in_(selected_service_ids),
        )).all()) if selected_service_ids else []

        room_cost = sum((Decimal(str(room_by_date[day].accounting_cost or 0)) for day in night_dates), Decimal("0"))
        product_rows = [ProductResource(
            resource_type="ROOM",
            resource_id=room.id,
            resource_name=room.room_type,
            quantity_per_package=1,
            unit_cost=room_cost,
            replaceable=False,
            required=True,
        )]
        unit_cost = room_cost
        partner_by_id = {item.id: item for item in selected_partners}
        for item in selections:
            resource_type = str(item["resource_type"])
            resource_id = int(item["resource_id"])
            quantity = max(1, int(item.get("quantity_per_package") or 1))
            if resource_type == "PARTNER_RESOURCE":
                partner = partner_by_id.get(resource_id)
                if not partner:
                    continue
                cost = Decimal(str(partner.settlement_price or 0))
                product_rows.append(ProductResource(
                    resource_type=resource_type,
                    resource_id=partner.id,
                    resource_name=partner.resource_name,
                    quantity_per_package=quantity,
                    unit_cost=cost,
                    replaceable=True,
                    required=partner.id == anchor_id,
                ))
                unit_cost += cost * quantity
            elif resource_type == "HOTEL_SERVICE":
                hotel_service = next((entry for entry in selected_service_rows if entry.id == resource_id), None)
                if not hotel_service:
                    continue
                cost = Decimal(str(hotel_service.unit_cost or 0))
                product_rows.append(ProductResource(
                    resource_type=resource_type,
                    resource_id=hotel_service.id,
                    resource_name=hotel_service.service_name,
                    quantity_per_package=quantity,
                    unit_cost=cost,
                    replaceable=hotel_service.replaceable,
                    required=True,
                ))
                unit_cost += cost * quantity

        if not any(row.resource_type == "PARTNER_RESOURCE" for row in product_rows):
            skipped_without_experiences += 1
            continue
        product.resources = product_rows
        product.party_size = party_size
        product.unit_cost = unit_cost.quantize(Decimal("0.01"))
        margin_floor = Decimal(str(product.minimum_gross_margin_requirement or "0.20"))
        minimum_price = (product.unit_cost / (Decimal("1") - margin_floor)).quantize(Decimal("0.01"), rounding=ROUND_UP)
        product.minimum_allowed_price = minimum_price
        product.suggested_price = max(Decimal(str(product.suggested_price or 0)), minimum_price)
        product.gross_profit = (product.suggested_price - product.unit_cost).quantize(Decimal("0.01"))
        product.gross_margin = (product.gross_profit / product.suggested_price).quantize(Decimal("0.000001")) if product.suggested_price else Decimal("0")
        room_cap = min(int(room_by_date[day].available_count or 0) for day in night_dates)
        resource_caps = [room_cap]
        resource_caps.extend(
            max(0, int(partner_by_id[int(item["resource_id"])].remaining_capacity or 0))
            // max(1, int(item.get("quantity_per_package") or 1))
            for item in selections
            if item["resource_type"] == "PARTNER_RESOURCE" and int(item["resource_id"]) in partner_by_id
        )
        service_by_id = {item.id: item for item in selected_service_rows}
        resource_caps.extend(
            max(0, int(service_by_id[int(item["resource_id"])].available_quantity or 0))
            // max(1, int(item.get("quantity_per_package") or 1))
            for item in selections
            if item["resource_type"] == "HOTEL_SERVICE" and int(item["resource_id"]) in service_by_id
        )
        physical_cap = min(resource_caps, default=0)
        listed_ceiling = int(product.listed_quantity or product.sale_quantity or physical_cap or 1)
        product.listed_quantity = max(1, listed_ceiling)
        product.sale_quantity = min(product.listed_quantity, physical_cap)
        product.status = "SOLD_OUT" if product.sale_quantity <= 0 else ("LOW_STOCK" if product.sale_quantity <= 2 else "ON_SALE")
        notes = product.experience_notes if isinstance(product.experience_notes, dict) else {}
        notes["stay_room_inventory_ids"] = [int(room_by_date[day].id) for day in night_dates[1:]]
        product.experience_notes = notes
        product.visitor_budget_limit = max(Decimal(str(product.visitor_budget_limit or 0)), product.suggested_price + Decimal("200"))
        product.price_anchor = product.suggested_price
        grouped_names: dict[date, list[str]] = {}
        for partner in sorted(
            selected_partners,
            key=lambda item: (
                item.available_date,
                item.start_time.isoformat() if item.start_time else "",
                item.resource_name,
            ),
        ):
            grouped_names.setdefault(partner.available_date, []).append(partner.resource_name)
        day_descriptions = [f"{day.strftime('%m月%d日')}安排{'、'.join(names)}" for day, names in sorted(grouped_names.items())]
        product.recommendation_reason = (
            f"按{nights + 1}天{nights}晚安排，将真实可预约体验分散到各日：{'；'.join(day_descriptions)}。"
            "行程保留每项资源的完整场次与转场时间；当日没有合适场次时保留自由活动，不虚构包含项目。"
        )
        refreshed += 1

    if refreshed:
        db.flush()
        reconcile_published_capacity(db, hotel_id)
    return {
        "updated": refreshed,
        "skipped_with_orders": skipped_with_orders,
        "skipped_without_stay": skipped_without_stay,
        "skipped_without_experiences": skipped_without_experiences,
    }


def _lookup(db: Session, model, hotel_id: int, field: str, value: str):
    return db.scalar(select(model).where(getattr(model, field) == value, getattr(model, "hotel_id") == hotel_id))


def _normalize_legacy_themes(db: Session, hotel_id: int) -> None:
    for product in db.scalars(select(TravelProduct).where(TravelProduct.hotel_id == hotel_id)):
        # Legacy showcase rows used local SVG/copy templates. Drop only those
        # placeholder assets: a generated poster (SVG payload) or an operator
        # uploaded asset must survive a restart.
        if product.product_code.startswith("SC-"):
            assets = product.marketing_assets if isinstance(product.marketing_assets, list) else []
            if not any(isinstance(asset, dict) and asset.get("poster_svg") for asset in assets):
                product.marketing_assets = []
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
    nights = int(plan.get("nights", 1) or 1)
    # 1 晚沿用口语化的「杭州一晚」，多日产品直接写「4天3晚」，方便推荐时区分。
    stay_suffix = f"{nights + 1}天{nights}晚" if nights > 1 else "杭州一晚"
    title = f"{name} · {stay_suffix}"
    content = (
        f"{date_label}，先把行李放进房间，再去 {partner.address or '杭州城里'} 体验 {partner.resource_name}。"
        "不用把一天排满，给散步、吃饭和临时发现留一点空白。"
    )
    reason = f"适合想把 {partner.resource_name} 排进杭州行程、又希望晚上住得舒服一点的你。"
    return title, content, reason


def seed_showcase_products(db: Session, hotel_id: int, target_date: date, *, variant_count: int = 8) -> dict[str, int]:
    """Seed a small, diverse merchant-approved product pool per date.

    It never calls a model at startup and deliberately leaves marketing assets
    empty. A hotel operator must press the product-detail "生成宣传素材" action
    to invoke the marketing Skill and the configured Wan image model. The rest
    of the resource pool remains available for operator-created products.
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
    # Group the catalogue by room type and seed a consecutive slice, so each
    # departure date gets several packages that share a room type.  That is what
    # fills the detail page's「同一房型的其他搭配」with real, bookable options
    # instead of a single card.
    ordered_plans = sorted(SHOWCASE_PLANS, key=lambda plan: str(plan["room"]))
    start = (target_date.toordinal() * 3) % len(ordered_plans)
    plans = []
    for offset in range(max(1, min(8, int(variant_count)))):
        plan = dict(ordered_plans[(start + offset) % len(ordered_plans)])
        # 每四组留一组 3 晚的多日产品，让智能推荐有 3 天以上的长行程可选。
        if offset % 4 == 3:
            plan["nights"] = 3
            plan["theme"] = f"{plan['theme']}·三日慢游"
            plan["price"] = str(int(plan["price"]) + 1200)
        plans.append(plan)
    created = 0
    for plan in plans:
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
                Merchant.hotel_id == hotel_id,
                PartnerResource.resource_name == plan["partner"],
                PartnerResource.available_date == target_date,
                PartnerResource.package_enabled.is_(True),
                PartnerResource.status == "AVAILABLE",
            )
        )
        if not room or not partner:
            continue
        nights = max(1, int(plan.get("nights", 1) or 1))
        stay_rows = [room]
        for night_offset in range(1, nights):
            overnight = db.scalar(
                select(RoomInventory).where(
                    RoomInventory.hotel_id == hotel_id,
                    RoomInventory.room_type == plan["room"],
                    RoomInventory.available_date == target_date + timedelta(days=night_offset),
                    RoomInventory.status == "AVAILABLE",
                    RoomInventory.available_count > 0,
                )
            )
            if overnight is None:
                stay_rows = []
                break
            stay_rows.append(overnight)
        if not stay_rows:
            continue
        room_capacity = min(int(item.available_count or 0) for item in stay_rows)
        room_cost = sum((Decimal(str(item.accounting_cost or 0)) for item in stay_rows), Decimal("0"))
        rows = [
            ProductResource(
                resource_type="ROOM",
                resource_id=room.id,
                resource_name=room.room_type,
                quantity_per_package=1,
                unit_cost=room_cost,
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
        unit_cost = room_cost + Decimal(partner.settlement_price) * int(plan["partner_quantity"])
        capacity = min(room_capacity, partner.remaining_capacity // max(1, int(plan["partner_quantity"])))
        if capacity <= 0:
            continue
        selected_partners = [partner]
        selected_names = {partner.resource_name}

        def conflicts_in_day(candidate: PartnerResource, current: list[PartnerResource]) -> bool:
            if not candidate.start_time or not candidate.end_time:
                return True
            return any(
                not item.start_time or not item.end_time
                or (candidate.start_time < item.end_time and item.start_time < candidate.end_time)
                for item in current
            )

        # Add a meal or complementary activity on the anchor date only when its
        # real session does not overlap the chosen core experience.
        extra_partners = list(
            db.scalars(
                select(PartnerResource)
                .join(PartnerResource.merchant)
                .where(
                    Merchant.hotel_id == hotel_id,
                    PartnerResource.available_date == target_date,
                    PartnerResource.package_enabled.is_(True),
                    PartnerResource.status == "AVAILABLE",
                    PartnerResource.resource_name != plan["partner"],
                    PartnerResource.remaining_capacity >= max(2, 3 if plan["crowd"] == "FAMILY" else 2),
                )
                .order_by(PartnerResource.remaining_capacity.desc())
            ).all()
        )
        food_extra = next(
            (item for item in extra_partners if item.resource_name not in selected_names
             and any(word in item.resource_name for word in ("美食", "甜品", "杭帮菜", "点茶", "下午茶", "咖啡", "夜市"))
             and not conflicts_in_day(item, selected_partners)),
            None,
        )
        if food_extra is not None:
            selected_partners.append(food_extra)
            selected_names.add(food_extra.resource_name)
        other_extra = next((item for item in extra_partners if item.resource_name not in selected_names and not conflicts_in_day(item, selected_partners)), None)
        for extra in (food_extra, other_extra):
            if extra is None:
                continue
            if any(row.resource_type == "PARTNER_RESOURCE" and row.resource_id == extra.id for row in rows):
                continue
            rows.append(
                ProductResource(
                    resource_type="PARTNER_RESOURCE",
                    resource_id=extra.id,
                    resource_name=extra.resource_name,
                    quantity_per_package=1,
                    unit_cost=extra.settlement_price,
                    replaceable=True,
                    required=False,
                )
            )
            unit_cost += Decimal(extra.settlement_price)
            capacity = min(capacity, int(extra.remaining_capacity or 0))
            if extra is not food_extra:
                selected_partners.append(extra)
            selected_names.add(extra.resource_name)

        # Spread at least one real, date-specific experience onto each later
        # trip day when a compatible, non-overlapping resource is available.
        for day_offset in range(1, nights + 1):
            visit_date = target_date + timedelta(days=day_offset)
            candidates = list(
                db.scalars(
                select(PartnerResource)
                .join(PartnerResource.merchant)
                .where(
                    Merchant.hotel_id == hotel_id,
                    PartnerResource.available_date == visit_date,
                        PartnerResource.package_enabled.is_(True),
                        PartnerResource.status == "AVAILABLE",
                        PartnerResource.remaining_capacity >= max(2, 3 if plan["crowd"] == "FAMILY" else 2),
                    )
                    .order_by(PartnerResource.start_time, PartnerResource.remaining_capacity.desc())
                ).all()
            )
            crowd_match = next(
                (item for item in candidates
                 if item.resource_name not in selected_names
                 and (plan["crowd"] in {tag.strip() for tag in str(item.suitable_crowds or "ALL").split(",")} or "ALL" in {tag.strip() for tag in str(item.suitable_crowds or "ALL").split(",")})
                 and item.start_time and item.end_time),
                None,
            )
            if crowd_match is None:
                continue
            rows.append(
                ProductResource(
                    resource_type="PARTNER_RESOURCE",
                    resource_id=crowd_match.id,
                    resource_name=crowd_match.resource_name,
                    quantity_per_package=1,
                    unit_cost=crowd_match.settlement_price,
                    replaceable=True,
                    required=False,
                )
            )
            selected_names.add(crowd_match.resource_name)
            unit_cost += Decimal(crowd_match.settlement_price)
            capacity = min(capacity, int(crowd_match.remaining_capacity or 0))
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
        if capacity <= 0:
            continue
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
            nights=nights,
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
            marketing_assets=[],
            recommendation_reason=reason,
            risk_message="这组日期的可预约名额不多，确认前会再次为你核对。" if quantity <= 2 else "",
            status="LOW_STOCK" if quantity <= 2 else "ON_SALE",
            resources=rows,
        )
        db.add(product)
        existing_themes.add(str(plan["theme"]))
        created += 1
    db.flush()
    refreshed = refresh_showcase_itineraries(db, hotel_id, start_date=target_date, end_date=target_date)
    reconcile_published_capacity(db, hotel_id)
    db.commit()
    return {"showcase_products": len(existing_themes), "created": created, "itineraries_refreshed": refreshed["updated"]}

