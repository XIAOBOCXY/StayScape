from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..agent import AgentOrchestrator
from ..agent.schemas import MarketingAgentOutput, ProductAgentOutput
from ..core.exceptions import AppError
from ..models import HotelService, Merchant, PartnerResource, ProductAdjustmentRecord, ProductResource, ResourceChangeEvent, RoomInventory, TravelProduct
from ..repositories.product_repository import products_referencing
from ..rules.availability_rule import resource_is_usable
from ..rules.capacity_rule import CapacityInput
from ..rules.crowd_rule import crowd_supported
from ..rules.product_validation_rule import PackageValidation, validate_package
from ..rules.time_rule import intervals_overlap, validate_interval
from ..rules.weather_rule import is_weather_supported
from ..schemas.products import GenerateProductRequest
from .inventory_service import ACTIVE_PRODUCT_STATUSES, ensure_publish_capacity, reconcile_published_capacity
from .knowledge_service import KnowledgeService
from .operations_insight_service import OperationsInsightService
from .weather_service import WeatherService
from .public_copy import route_proximity


DEFAULT_QUANTITIES = {"BREAKFAST": 3, "LATE_CHECKOUT": 1}


def _trip_last_date(request: GenerateProductRequest) -> date:
    return request.target_date + timedelta(days=max(1, int(getattr(request, "nights", 1) or 1)))


def _is_dining_resource(resource: PartnerResource) -> bool:
    text = f"{resource.category or ''} {resource.resource_name or ''}".upper()
    if any(word in text for word in ("手作", "制作", "陶艺", "课堂", "烘焙", "工作坊")):
        return False
    return any(word in text for word in ("DINING", "RESTAURANT", "餐饮", "餐厅", "用餐", "午餐", "晚餐", "杭帮菜", "美食", "FOOD"))


def _partner_daypart(resource: PartnerResource) -> tuple[str, int]:
    start = resource.start_time
    if start is None:
        return "UNSCHEDULED", 1
    minute = start.hour * 60 + start.minute
    end = resource.end_time
    if end is not None and not _is_dining_resource(resource):
        duration = end.hour * 60 + end.minute - minute
        if duration <= 0:
            duration += 24 * 60
        # A long attraction (for example a theme park) is a day plan by
        # itself. Do not squeeze another paid activity into the same date.
        if duration >= 240:
            return "ALL_DAY", 1
    if 11 * 60 + 30 <= minute < 13 * 60 + 30:
        return "MIDDAY", 1
    if _is_dining_resource(resource):
        if 17 * 60 <= minute < 20 * 60:
            return "DINNER", 1
        return "MEAL_OTHER", 0
    if minute < 11 * 60 + 30:
        return "MORNING", 2
    if minute < 17 * 60 + 30:
        return "AFTERNOON", 2
    return "EVENING", 1


def _partner_transfer_issue(resources: list[PartnerResource]) -> str | None:
    by_date: dict[date, list[PartnerResource]] = {}
    for item in resources:
        by_date.setdefault(item.available_date, []).append(item)
    for day_resources in by_date.values():
        scheduled = sorted(
            (item for item in day_resources if item.start_time and item.end_time),
            key=lambda item: item.start_time,
        )
        for previous, following in zip(scheduled, scheduled[1:]):
            if not previous.address or not following.address or previous.address.strip() == following.address.strip():
                continue
            gap = int((following.start_time.hour * 60 + following.start_time.minute) - (previous.end_time.hour * 60 + previous.end_time.minute))
            if gap < 0:
                continue
            required = int(route_proximity(previous.address, following.address).get("buffer_minutes") or 30)
            if gap < required:
                return f"{previous.resource_name}结束后到{following.resource_name}开始仅有 {gap} 分钟；按地点建议至少预留 {required} 分钟转场，请调整场次或拆分产品。"
    return None


NON_EXCLUSIVE_SERVICE_TYPES = {"BREAKFAST", "PARKING", "LUGGAGE_STORAGE", "LATE_CHECKOUT"}

MARKETING_STYLE_GUIDES: dict[str, dict[str, str]] = {
    "ARTISTIC": {"label": "文艺叙事", "direction": "用有画面感的旅行随笔写法，从具体时刻开场，写光线、声音和动作；克制、温柔，不硬推销。"},
    "PROMOTIONAL": {"label": "直接推荐", "direction": "先说适合谁和怎么玩，再给出真实包含内容与预约提醒；可以利落分点，但不得虚构折扣、限量、评价或价格。"},
    "EMPATHETIC": {"label": "情绪共鸣", "direction": "从旅行者想放松、想陪伴或想换节奏的心情切入；语气像懂你的朋友，温暖但不煽情。"},
    "SEEDING": {"label": "轻松种草", "direction": "用朋友分享周末发现的口吻：首句有钩子，接着写2到3个值得去的具体理由与可感知的细节；短句友好。"},
}


def marketing_style_direction(style: str, extra_direction: str = "") -> str:
    guide = MARKETING_STYLE_GUIDES.get(style, MARKETING_STYLE_GUIDES["SEEDING"])
    extra = f" 经营者补充方向：{extra_direction.strip()}" if extra_direction.strip() else ""
    return (
        f"营销文案风格：{guide['label']}。{guide['direction']} "
        "面向游客的标题、推荐理由、风险提示和素材中不要出现规则引擎、库存、容量、成本、毛利、Demo、接口、技能或内部校验等后台术语。"
        "每一套内容都要从同行关系、一个具体体验瞬间和一个可感知的杭州地点切入；标题不超过22个中文字符，正文用2到3句短句形成画面，避免反复使用“住一晚、慢慢玩、刚刚好”等套话。可参考旅行平台、小红书与短视频常见的节奏，但不得模仿具体作者或账号。"
        f"{extra}"
    )


def blocks_schedule(service: HotelService) -> bool:
    """Only bookable activities occupy an exclusive time slot.

    Breakfast, parking, luggage storage and late checkout are entitlements with
    broad windows. They can coexist with a cultural activity and should not
    prevent a second alternative package from being generated.
    """
    return service.service_type not in NON_EXCLUSIVE_SERVICE_TYPES


def json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


class ProductService:
    def __init__(self, db: Session, hotel_id: int, orchestrator: AgentOrchestrator | None = None, *, intelligence_context: dict[str, Any] | None = None) -> None:
        self.db = db
        self.hotel_id = hotel_id
        self.orchestrator = orchestrator or AgentOrchestrator(db, hotel_id=hotel_id, source_channel="WEB_HOTEL", actor_role="HOTEL_OPERATOR")
        self.intelligence_context = intelligence_context or {}

    def ensure_publish_capacity(self, product: TravelProduct) -> list[dict[str, Any]]:
        return ensure_publish_capacity(self.db, product)

    def _room(self, request: GenerateProductRequest) -> RoomInventory:
        query = select(RoomInventory).where(RoomInventory.hotel_id == self.hotel_id, RoomInventory.available_date == request.target_date)
        if request.room_inventory_id:
            query = query.where(RoomInventory.id == request.room_inventory_id)
        else:
            # An automatically generated candidate must choose a room that can
            # actually host its declared package size.  Keep an explicitly
            # chosen incompatible room visible to the validator below, so the
            # hotel receives a precise correction instead of a silent swap.
            query = query.where(RoomInventory.max_guests >= request.party_size)
        room = self.db.scalar(query.order_by(RoomInventory.available_count.desc()))
        if not room:
            raise AppError("ROOM_INVENTORY_INSUFFICIENT", "没有找到符合入住日期的临期客房", field="room_inventory_id", retryable=True)
        if room.available_count <= 0 or room.status in {"SOLD_OUT", "DISABLED"}:
            raise AppError("ROOM_INVENTORY_INSUFFICIENT", "客房库存不足或已停用", field="room_inventory_id", retryable=True)
        if request.party_size > room.max_guests:
            raise AppError(
                "PARTY_SIZE_NOT_SUPPORTED",
                f"{room.room_type}最多接待 {room.max_guests} 人，请减少套餐人数或选择其他房型",
                field="party_size",
                retryable=True,
            )
        return room

    def _default_selections(
        self,
        request: GenerateProductRequest,
        room: RoomInventory,
        *,
        variant_index: int = 0,
        base_selections: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Build a trip-length itinerary from selected anchors and live inventory.

        Explicitly selected resources are anchors, not a reason to stop looking
        for complementary experiences. Every addition is still checked against
        date, stock, time, transfer, daypart and budget constraints.
        """
        selections = [dict(item) for item in (base_selections or [])]
        services = list(self.db.scalars(select(HotelService).where(
            HotelService.hotel_id == self.hotel_id,
            HotelService.available_date == request.target_date,
            HotelService.status == "AVAILABLE",
        ).order_by(HotelService.id)).all())
        if base_selections is None:
            breakfast = next((item for item in services if item.service_type == "BREAKFAST"), None)
            late_checkout = next((item for item in services if item.service_type == "LATE_CHECKOUT"), None)
            if breakfast:
                selections.append({"resource_type": "HOTEL_SERVICE", "resource_id": breakfast.id, "quantity_per_package": request.party_size})
            if late_checkout:
                selections.append({"resource_type": "HOTEL_SERVICE", "resource_id": late_checkout.id, "quantity_per_package": 1})

        service_ids = {int(item["resource_id"]) for item in selections if item["resource_type"] == "HOTEL_SERVICE"}
        selected_services = {
            item.id: item
            for item in self.db.scalars(
                select(HotelService).where(
                    HotelService.hotel_id == self.hotel_id,
                    HotelService.id.in_(service_ids),
                )
            ).all()
        } if service_ids else {}
        all_partners = list(self.db.scalars(select(PartnerResource).join(Merchant).options(
            selectinload(PartnerResource.merchant)
        ).where(
            Merchant.hotel_id == self.hotel_id,
            PartnerResource.available_date >= request.target_date,
            PartnerResource.available_date <= _trip_last_date(request),
        ).order_by(PartnerResource.available_date, PartnerResource.id)).unique().all())
        eligible = [item for item in all_partners if self._partner_candidate(item, request) and _partner_daypart(item)[1] > 0]

        theme_text = f"{request.theme} {request.target_crowd}".lower()
        preferred_categories: set[str] = set()
        if any(word in theme_text for word in ("乐园", "游乐", "theme park")):
            preferred_categories.update({"THEME_PARK", "KIDS"})
        elif any(word in theme_text for word in ("运动", "攀岩", "卡丁车", "刺激", "sport")):
            preferred_categories.update({"SPORT", "ENTERTAINMENT"})
        elif any(word in theme_text for word in ("夜游", "夜景", "夜生活", "night")):
            preferred_categories.update({"NIGHTLIFE", "ENTERTAINMENT", "PHOTO"})
        elif any(word in theme_text for word in ("旅拍", "摄影", "photo")):
            preferred_categories.add("PHOTO")
        elif any(word in theme_text for word in ("美食", "咖啡", "甜品", "food")):
            preferred_categories.add("FOOD")
        elif any(word in theme_text for word in ("自然", "湿地", "动物", "nature")):
            preferred_categories.add("NATURE")
        elif any(word in theme_text for word in ("演出", "剧场", "performance")):
            preferred_categories.add("PERFORMANCE")
        elif any(word in theme_text for word in ("漫游", "城市", "city")):
            preferred_categories.update({"CITY_WALK", "PHOTO", "FOOD"})
        elif any(word in theme_text for word in ("茶", "点茶", "tea")):
            preferred_categories.update({"TEA", "CULTURE"})
        elif any(word in theme_text for word in ("非遗", "手作", "文化", "craft")):
            preferred_categories.add("CULTURE")
        elif request.target_crowd == "FAMILY":
            preferred_categories.update({"KIDS", "THEME_PARK", "NATURE", "CULTURE"})
        elif request.target_crowd == "COUPLE":
            preferred_categories.update({"PHOTO", "NIGHTLIFE", "FOOD", "ENTERTAINMENT"})
        elif request.target_crowd == "FRIENDS":
            preferred_categories.update({"SPORT", "ENTERTAINMENT", "NIGHTLIFE"})
        elif request.target_crowd == "SOLO":
            preferred_categories.update({"FOOD", "CITY_WALK", "CULTURE"})
        else:
            preferred_categories.update({"FOOD", "CITY_WALK", "NIGHTLIFE"})
        if request.weather == "RAIN":
            eligible.sort(key=lambda item: (item.category not in preferred_categories, not item.indoor, item.settlement_price, item.id))
        elif request.weather == "SUNNY":
            eligible.sort(key=lambda item: (item.category not in preferred_categories, item.indoor, item.settlement_price, item.id))
        else:
            eligible.sort(key=lambda item: (item.category not in preferred_categories, not item.indoor, item.settlement_price, item.id))

        selected_ids = {int(item["resource_id"]) for item in selections if item["resource_type"] == "PARTNER_RESOURCE"}
        chosen = [item for item in all_partners if item.id in selected_ids]
        primary_pool = [item for item in eligible if item.start_time and item.end_time] or eligible
        if not chosen and primary_pool:
            chosen = [primary_pool[variant_index % len(primary_pool)]]
            primary = chosen[0]
            selections.append({"resource_type": "PARTNER_RESOURCE", "resource_id": primary.id, "quantity_per_package": request.party_size})
            selected_ids.add(primary.id)

        part_counts: dict[tuple[date, str], int] = {}
        for item in chosen:
            part, _ = _partner_daypart(item)
            key = (item.available_date, part)
            part_counts[key] = part_counts.get(key, 0) + 1
        nightly_rooms = [room]
        for offset in range(1, max(1, int(request.nights or 1))):
            night_date = request.target_date + timedelta(days=offset)
            night_room = self.db.scalar(
                select(RoomInventory).where(
                    RoomInventory.hotel_id == self.hotel_id,
                    RoomInventory.available_date == night_date,
                    RoomInventory.room_type == room.room_type,
                    RoomInventory.max_guests >= request.party_size,
                    RoomInventory.status == "AVAILABLE",
                    RoomInventory.available_count > 0,
                ).order_by(RoomInventory.available_count.desc())
            )
            if night_room is not None:
                nightly_rooms.append(night_room)
        base_cost = sum((Decimal(str(item.accounting_cost or 0)) for item in nightly_rooms), Decimal("0"))
        for service_id, service in selected_services.items():
            row = next((item for item in selections if item["resource_type"] == "HOTEL_SERVICE" and int(item["resource_id"]) == service_id), {})
            base_cost += service.unit_cost * int(row.get("quantity_per_package") or 1)

        offset = variant_index % len(eligible) if eligible else 0
        rotated = eligible[offset:] + eligible[:offset]
        rotation_rank = {item.id: index for index, item in enumerate(rotated)}
        margin = Decimal(request.minimum_gross_margin or 0)
        # Re-rank after every selection. A one-time sort can still exhaust all
        # activities on the first available date before it reaches day two.
        while True:
            options: list[tuple[tuple, PartnerResource]] = []
            for candidate in eligible:
                if candidate.id in selected_ids or any(str(item.resource_name) == str(candidate.resource_name) for item in chosen):
                    continue
                part, cap = _partner_daypart(candidate)
                if cap <= 0 or not candidate.start_time or not candidate.end_time:
                    continue
                part_key = (candidate.available_date, part)
                if part_counts.get(part_key, 0) >= cap:
                    continue
                same_day = [item for item in chosen if item.available_date == candidate.available_date]
                if part == "ALL_DAY" and same_day:
                    continue
                if any(_partner_daypart(item)[0] == "ALL_DAY" for item in same_day):
                    continue
                if any(not item.start_time or not item.end_time for item in same_day):
                    continue
                if any(intervals_overlap(item.start_time, item.end_time, candidate.start_time, candidate.end_time) for item in same_day):
                    continue
                if any(
                    service.available_date == candidate.available_date and blocks_schedule(service)
                    and intervals_overlap(service.start_time, service.end_time, candidate.start_time, candidate.end_time)
                    for service in selected_services.values()
                ):
                    continue
                if _partner_transfer_issue([*same_day, candidate]):
                    continue
                if request.visitor_budget is not None:
                    cost = base_cost + sum(item.settlement_price * request.party_size for item in [*chosen, candidate])
                    if margin >= 1 or max(room.minimum_price, cost / (Decimal("1") - margin)) > request.visitor_budget:
                        continue
                # Balance both the number of items per date and the morning,
                # afternoon, evening slots. Full-day experiences naturally
                # reserve one complete date instead of being squeezed in later.
                rank = (
                    len(same_day),
                    part_counts.get(part_key, 0),
                    candidate.category not in preferred_categories,
                    _is_dining_resource(candidate),
                    0 if part == "ALL_DAY" else 1,
                    candidate.available_date,
                    candidate.start_time or time.max,
                    rotation_rank.get(candidate.id, candidate.id),
                )
                options.append((rank, candidate))
            if not options:
                break
            _, candidate = min(options, key=lambda item: item[0])
            part, _ = _partner_daypart(candidate)
            part_key = (candidate.available_date, part)
            chosen.append(candidate)
            selected_ids.add(candidate.id)
            part_counts[part_key] = part_counts.get(part_key, 0) + 1
            selections.append({"resource_type": "PARTNER_RESOURCE", "resource_id": candidate.id, "quantity_per_package": request.party_size})
        return selections

    def _variant_manual_selections(
        self,
        request: GenerateProductRequest,
        selections: list[dict[str, Any]],
        *,
        variant_index: int,
    ) -> list[dict[str, Any]]:
        """Turn a hand-picked *set of options* into one compatible variant.

        Operators commonly tick several sessions as alternatives.  Treating
        every checked session as a compulsory part of the same itinerary made
        otherwise valid proposals fail with a time-conflict error.  Services
        stay selected; overlapping partner sessions are rotated across the
        requested variants.  Non-overlapping activities can still coexist in
        one itinerary when an operator intentionally selects them.
        """
        service_rows = [item for item in selections if item["resource_type"] == "HOTEL_SERVICE"]
        partner_rows = [item for item in selections if item["resource_type"] == "PARTNER_RESOURCE"]
        if len(partner_rows) <= 1:
            return selections

        service_ids = [int(item["resource_id"]) for item in service_rows]
        services = {
            item.id: item
            for item in self.db.scalars(
                select(HotelService).where(HotelService.hotel_id == self.hotel_id, HotelService.id.in_(service_ids))
            ).all()
        }
        slots: list[tuple[date, time | None, time | None, str]] = [
            (service.available_date, service.start_time, service.end_time, service.service_name)
            for row in service_rows
            if (service := services.get(int(row["resource_id"]))) and blocks_schedule(service)
        ]

        partner_ids = [int(item["resource_id"]) for item in partner_rows]
        partners = {
            item.id: item
            for item in self.db.scalars(
                select(PartnerResource)
                .join(Merchant)
                .options(selectinload(PartnerResource.merchant))
                .where(PartnerResource.id.in_(partner_ids), Merchant.hotel_id == self.hotel_id)
            ).unique().all()
        }
        # Rotate the order while preserving the operator's deliberate ordering.
        offset = variant_index % len(partner_rows)
        rotated = partner_rows[offset:] + partner_rows[:offset]
        rotated_order = {int(row["resource_id"]): index for index, row in enumerate(rotated)}
        rotated.sort(key=lambda row: (
            0 if (partner := partners.get(int(row["resource_id"]))) and _partner_daypart(partner)[0] == "ALL_DAY" else 1,
            rotated_order.get(int(row["resource_id"]), 0),
        ))
        accepted: list[dict[str, Any]] = []
        accepted_names: set[str] = set()
        part_counts: dict[tuple[date, str], int] = {}
        for row in rotated:
            partner = partners.get(int(row["resource_id"]))
            if not partner:
                # Let the authoritative validation below report an invalid ID.
                accepted.append(row)
                continue
            resource_name = str(partner.resource_name or "").strip().casefold()
            if resource_name and resource_name in accepted_names:
                continue
            part, cap = _partner_daypart(partner)
            part_key = (partner.available_date, part)
            if part_counts.get(part_key, 0) >= cap:
                continue
            same_day_partners = [
                existing for accepted_row in accepted
                if (existing := partners.get(int(accepted_row["resource_id"]))) is not None
                and existing.available_date == partner.available_date
            ]
            if part == "ALL_DAY" and same_day_partners:
                continue
            if any(_partner_daypart(existing)[0] == "ALL_DAY" for existing in same_day_partners):
                continue
            if any(day == partner.available_date and intervals_overlap(partner.start_time, partner.end_time, start, end) for day, start, end, _ in slots):
                continue
            accepted.append(row)
            if resource_name:
                accepted_names.add(resource_name)
            slots.append((partner.available_date, partner.start_time, partner.end_time, partner.resource_name))
            part_counts[part_key] = part_counts.get(part_key, 0) + 1

        # Preserve the original payload if there is no valid alternative; the
        # normal validation will return a concrete operator-facing reason.
        return service_rows + (accepted or partner_rows)

    def _partner_candidate(self, resource: PartnerResource, request: GenerateProductRequest) -> bool:
        merchant = resource.merchant
        return bool(
            merchant
            and request.target_date <= resource.available_date <= _trip_last_date(request)
            and resource_is_usable(merchant_status=merchant.cooperation_status, package_enabled=resource.package_enabled, resource_status=resource.status, capacity=resource.remaining_capacity, source_type=resource.source_type)
            and resource.remaining_capacity >= request.party_size
        )

    def _payload(self, request: GenerateProductRequest, room: RoomInventory, selections: list[dict[str, Any]], *, variant_index: int = 0) -> dict[str, Any]:
        services = list(self.db.scalars(select(HotelService).where(HotelService.hotel_id == self.hotel_id, HotelService.available_date == request.target_date)).all())
        partners = list(self.db.scalars(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(Merchant.hotel_id == self.hotel_id, PartnerResource.available_date >= request.target_date, PartnerResource.available_date <= _trip_last_date(request))).unique().all())
        allowed_ids = {(str(item["resource_type"]), int(item["resource_id"])) for item in selections}
        # Keep the full multi-day evidence in the operations UI, but only send
        # evidence usable by this specific product date to the generation skill.
        # Cross-date resource rows add prompt size without changing this package.
        raw_insights = self.intelligence_context.get("insights")
        if isinstance(raw_insights, dict):
            operations_insights = dict(raw_insights)
            target_date = request.target_date.isoformat()
            for key in ("resource_evidence", "service_evidence"):
                rows = operations_insights.get(key)
                if isinstance(rows, list):
                    operations_insights[key] = [
                        row for row in rows
                        if isinstance(row, dict) and str(row.get("available_date") or "") == target_date
                    ]
        else:
            operations_insights = raw_insights
        return {
            "hotel_id": self.hotel_id,
            "target_date": request.target_date.isoformat(),
            "nights": int(getattr(request, "nights", 1) or 1),
            "trip_days": int(getattr(request, "nights", 1) or 1) + 1,
            "weather": request.weather,
            "target_crowd": request.target_crowd,
            "party_size": request.party_size,
            "theme": request.theme,
            "creative_direction": request.creative_direction,
            "variant_index": variant_index,
            "variant_total": request.variant_count,
            "visitor_budget": str(request.visitor_budget) if request.visitor_budget is not None else "未指定",
            "preferred_price": str(request.preferred_price) if request.preferred_price is not None else "由房价下限决定",
            "room_inventory": {"id": room.id, "room_type": room.room_type, "max_guests": room.max_guests, "features": room.features, "suitable_crowds": room.suitable_crowds, "tags": room.tags, "available_count": room.available_count},
            "requested_selections": selections,
            "allowed_hotel_services": [{"id": item.id, "service_name": item.service_name, "service_type": item.service_type, "available_date": item.available_date.isoformat(), "status": item.status, "start_time": item.start_time.strftime("%H:%M") if item.start_time else None, "end_time": item.end_time.strftime("%H:%M") if item.end_time else None, "unit_cost": str(item.unit_cost)} for item in services if item.status == "AVAILABLE" and ("HOTEL_SERVICE", item.id) in allowed_ids],
            "allowed_partner_resources": [{"id": item.id, "resource_name": item.resource_name, "category": item.category, "available_date": item.available_date.isoformat(), "description": item.description, "address": item.address, "start_time": item.start_time.strftime("%H:%M") if item.start_time else None, "end_time": item.end_time.strftime("%H:%M") if item.end_time else None, "remaining_capacity": item.remaining_capacity, "settlement_price": str(item.settlement_price), "indoor": item.indoor, "suitable_crowds": item.suitable_crowds, "weather_tags": item.weather_tags, "source_type": item.source_type, "status": item.status, "package_enabled": item.package_enabled, "merchant_status": item.merchant.cooperation_status if item.merchant else "TERMINATED"} for item in partners if ("PARTNER_RESOURCE", item.id) in allowed_ids and item.merchant and resource_is_usable(merchant_status=item.merchant.cooperation_status, package_enabled=item.package_enabled, resource_status=item.status, capacity=item.remaining_capacity, source_type=item.source_type)],
            # These facts are advisory context only. IDs, capacities, prices and
            # constraints remain selected and checked below in FastAPI.
            "weather_forecast": self.intelligence_context.get("weather"),
            "operations_insights": operations_insights,
            "travel_knowledge": self.intelligence_context.get("knowledge", []),
            "tourism_planning_context": self.intelligence_context.get("tourism_planning_context", {}),
        }

    def _marketing_assets(self, assets, *, product_name: str, theme: str, target_crowd: str, weather: str, target_date: object, price: Decimal | str, room: RoomInventory, resources: list[ProductResource], variant_index: int = 0, copy_style: str = "SEEDING", generated_image: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Keep channel copy assets; discard legacy poster assets."""
        rendered: list[dict[str, Any]] = []
        for asset in assets:
            data = asset.model_dump(mode="json") if hasattr(asset, "model_dump") else dict(asset)
            if data.get("asset_type") == "POSTER":
                continue
            data["copy_style"] = copy_style
            rendered.append(data)
        return rendered

    def generate(self, request: GenerateProductRequest, *, variant_index: int = 0, initial_status: str = "DRAFT") -> tuple[TravelProduct, dict[str, Any], str, bool]:
        room = self._room(request)
        stay_rooms = [room]
        for offset in range(1, max(1, int(request.nights or 1))):
            night_date = request.target_date + timedelta(days=offset)
            night_room = self.db.scalar(
                select(RoomInventory)
                .where(
                    RoomInventory.hotel_id == self.hotel_id,
                    RoomInventory.available_date == night_date,
                    RoomInventory.room_type == room.room_type,
                    RoomInventory.max_guests >= request.party_size,
                    RoomInventory.status == "AVAILABLE",
                    RoomInventory.available_count > 0,
                )
                .order_by(RoomInventory.available_count.desc())
            )
            if night_room is None:
                raise AppError(
                    "STAY_RANGE_UNAVAILABLE",
                    f"{room.room_type} 在 {night_date.isoformat()} 没有可接待 {request.party_size} 人的空房；请调整入住日期、天数或房型。",
                    field="nights",
                    retryable=True,
                )
            stay_rooms.append(night_room)
        manual_selections = [item.model_dump() for item in request.resource_selections]
        # Resolve a compatible multi-day set before the creative call. Selected
        # experiences anchor the schedule; the model never chooses inventory.
        selections = (
            self._variant_manual_selections(request, manual_selections, variant_index=variant_index)
            if manual_selections
            else self._default_selections(request, room, variant_index=variant_index)
        )
        if manual_selections:
            selections = self._default_selections(
                request, room, variant_index=variant_index, base_selections=selections
            )
        selected_partner_ids = [int(item["resource_id"]) for item in selections if item["resource_type"] == "PARTNER_RESOURCE"]
        selected_partners_for_arrival = list(self.db.scalars(
            select(PartnerResource).where(
                PartnerResource.id.in_(selected_partner_ids),
                PartnerResource.available_date == request.target_date,
            )
        ).all()) if selected_partner_ids else []
        early_start = any(item.start_time is not None and item.start_time.hour < 15 for item in selected_partners_for_arrival)
        baggage_service = self.db.scalar(
            select(HotelService).where(
                HotelService.hotel_id == self.hotel_id,
                HotelService.available_date == request.target_date,
                HotelService.status == "AVAILABLE",
                HotelService.available_quantity > 0,
                or_(HotelService.service_type == "LUGGAGE_STORAGE", HotelService.service_name.contains("行李寄存")),
            ).order_by(HotelService.id)
        )
        selected_service_ids = {int(item["resource_id"]) for item in selections if item["resource_type"] == "HOTEL_SERVICE"}
        if baggage_service is not None and baggage_service.id not in selected_service_ids:
            # Include the hotel-front desk as the first itinerary stop when
            # an experience starts before check-in, and as a checkout-day
            # benefit for multi-day visitor itineraries.
            selections.append({"resource_type": "HOTEL_SERVICE", "resource_id": baggage_service.id, "quantity_per_package": 1})
        elif early_start and baggage_service is None:
            raise AppError(
                "LUGGAGE_STORAGE_UNAVAILABLE",
                f"{request.target_date.isoformat()} 的首项体验早于15:00入住时间，请先补充当天的行李寄存服务。",
                field="resource_selections",
                retryable=True,
            )
        payload = self._payload(request, room, selections, variant_index=variant_index)
        agent_result = self.orchestrator.generate_product(payload)
        output: ProductAgentOutput = agent_result.value  # type: ignore[assignment]
        # The agent is responsible for travel copy, not for authoritative
        # allocation IDs.  A malformed or stale model ID must never turn a
        # valid stock-backed automatic plan into a failed request.
        requested_by_type = {(item["resource_type"], item["resource_id"]): item for item in selections}
        # Resource selection is deterministic and locked before the LLM is
        # called.  Treat model IDs as content hints only: allowing the model to
        # substitute arbitrary IDs was the source of time-overlap failures.
        selected_services = [item.id for item in self.db.scalars(select(HotelService).where(HotelService.id.in_([resource_id for resource_type, resource_id in requested_by_type if resource_type == "HOTEL_SERVICE"]), HotelService.hotel_id == self.hotel_id)).all()]
        selected_partners = list(self.db.scalars(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(PartnerResource.id.in_([resource_id for resource_type, resource_id in requested_by_type if resource_type == "PARTNER_RESOURCE"]), Merchant.hotel_id == self.hotel_id)).unique().all())
        if len(selected_services) != sum(1 for resource_type, _ in requested_by_type if resource_type == "HOTEL_SERVICE") or len(selected_partners) != sum(1 for resource_type, _ in requested_by_type if resource_type == "PARTNER_RESOURCE"):
            raise AppError("RESOURCE_SELECTION_INVALID", "选择的资源不存在或不属于当前酒店", field="resource_selections")

        services = [self.db.get(HotelService, item) for item in selected_services]
        resource_rows: list[ProductResource] = [ProductResource(resource_type="ROOM", resource_id=room.id, resource_name=room.room_type, quantity_per_package=1, unit_cost=room.accounting_cost, replaceable=False, required=True)]
        capacity_inputs = [CapacityInput(f"{night_room.room_type} · {night_room.available_date}", night_room.available_count, 1) for night_room in stay_rooms]
        unit_cost = sum((Decimal(str(night_room.accounting_cost or 0)) for night_room in stay_rooms), Decimal("0"))
        warnings: list[str] = []
        compatibility_notes: list[str] = []
        weather_label = {"RAIN": "有雨", "SUNNY": "晴天", "CLOUDY": "多云"}.get(str(request.weather or "").upper(), "当前天气")
        crowd_label = {"FAMILY": "亲子家庭", "COUPLE": "两人同行", "FRIENDS": "朋友同行", "SOLO": "独自出行", "LOCAL_WEEKEND": "本地周末客", "ALL": "不限客群"}.get(str(request.target_crowd or "").upper(), "当前客群")
        crowd_names = {"FAMILY": "亲子家庭", "COUPLE": "两人同行", "FRIENDS": "朋友同行", "SOLO": "独自出行", "LOCAL_WEEKEND": "本地周末客", "ALL": "不限人群"}
        daypart_counts: dict[tuple[date, str], int] = {}
        for partner in selected_partners:
            part, cap = _partner_daypart(partner)
            key = (partner.available_date, part)
            daypart_counts[key] = daypart_counts.get(key, 0) + 1
            if daypart_counts[key] > cap:
                raise AppError("DAYPART_CAPACITY", f"{partner.available_date.isoformat()} 的{part}时段最多安排 {cap} 项", field="resource_selections", retryable=True)
        schedule_slots: list[tuple[date, time | None, time | None, str]] = []
        for service in services:
            if service is None:
                continue
            requested_quantity = requested_by_type.get(("HOTEL_SERVICE", service.id), {}).get("quantity_per_package", DEFAULT_QUANTITIES.get(service.service_type, 1))
            # Explicit operator selections are authoritative; a generated
            # draft must not silently change their per-package quantities.
            q = requested_quantity
            self._validate_service(service, request, q)
            if blocks_schedule(service) and any(day == service.available_date and intervals_overlap(service.start_time, service.end_time, start, end) for day, start, end, _ in schedule_slots):
                raise AppError("TIME_CONFLICT", f"酒店服务{service.service_name}与套餐内其他活动时间冲突", field="resource_selections", retryable=True)
            resource_rows.append(ProductResource(resource_type="HOTEL_SERVICE", resource_id=service.id, resource_name=service.service_name, quantity_per_package=q, unit_cost=service.unit_cost, replaceable=service.replaceable, required=True))
            capacity_inputs.append(CapacityInput(service.service_name, service.available_quantity, q))
            unit_cost += service.unit_cost * q
            if blocks_schedule(service):
                schedule_slots.append((service.available_date, service.start_time, service.end_time, service.service_name))
        for partner in selected_partners:
            requested_quantity = requested_by_type.get(("PARTNER_RESOURCE", partner.id), {}).get("quantity_per_package", 1)
            q = requested_quantity
            self._validate_partner(partner, request, q)
            if not is_weather_supported(partner.weather_tags, request.weather):
                compatibility_notes.append(
                    f"天气提示：{partner.resource_name}登记的适用天气未覆盖{weather_label}，仍可生成；请在行程建议中说明现场天气风险，并提供合适的替代体验。"
                )
            if not crowd_supported(partner.suitable_crowds, request.target_crowd, minimum_age=partner.minimum_age, maximum_age=partner.maximum_age):
                tags = [tag.strip().upper() for tag in str(partner.suitable_crowds or "").split(",") if tag.strip()]
                suitable = "、".join(crowd_names.get(tag, "其他客群") for tag in tags) or "未注明"
                compatibility_notes.append(
                    f"客群提示：当前按{crowd_label}设计，但{partner.resource_name}登记适合{suitable}；保留该体验，商品说明中应提示运营确认接待与年龄要求。"
                )
            if any(day == partner.available_date and intervals_overlap(partner.start_time, partner.end_time, start, end) for day, start, end, _ in schedule_slots):
                raise AppError("TIME_CONFLICT", f"文化体验{partner.resource_name}与套餐内其他活动时间冲突", field="resource_selections", retryable=True)
            resource_rows.append(ProductResource(resource_type="PARTNER_RESOURCE", resource_id=partner.id, resource_name=partner.resource_name, quantity_per_package=q, unit_cost=partner.settlement_price, replaceable=True, required=True))
            capacity_inputs.append(CapacityInput(partner.resource_name, partner.remaining_capacity, q))
            unit_cost += partner.settlement_price * q
            schedule_slots.append((partner.available_date, partner.start_time, partner.end_time, partner.resource_name))
        transfer_issue = _partner_transfer_issue(selected_partners)
        if transfer_issue:
            raise AppError("TRAVEL_BUFFER_INSUFFICIENT", transfer_issue, field="resource_selections", retryable=True)
        if len(resource_rows) < 2:
            raise AppError("VALIDATION_ERROR", "套餐至少需要客房和一项酒店服务或文旅体验", field="resource_selections")
        stay_minimum_price = sum((Decimal(str(night_room.minimum_price or 0)) for night_room in stay_rooms), Decimal("0"))
        validation = validate_package(capacity_inputs=capacity_inputs, unit_cost=unit_cost, room_minimum_price=stay_minimum_price, minimum_gross_margin=request.minimum_gross_margin, visitor_budget=request.visitor_budget, preferred_price=request.preferred_price, warnings=warnings)
        if validation.capacity.sale_quantity <= 0:
            raise AppError("CAPACITY_INSUFFICIENT", "组合资源无法支持一套产品", field="resource_selections", retryable=True, details=validation.as_dict())
        if validation.capacity.sale_quantity <= 2:
            warnings.append("当前套餐库存紧张，建议及时确认预约意向")
        product = TravelProduct(
            hotel_id=self.hotel_id,
            product_code=f"SS-{request.target_date.strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}",
            product_name=output.product_name,
            theme=output.theme,
            target_crowd=request.target_crowd,
            party_size=request.party_size,
            nights=getattr(request, "nights", 1) or 1,
            weather=request.weather,
            target_date=request.target_date,
            room_inventory_id=room.id,
            listed_quantity=validation.capacity.sale_quantity,
            sale_quantity=validation.capacity.sale_quantity,
            unit_cost=validation.pricing.unit_cost,
            minimum_allowed_price=validation.pricing.minimum_allowed_price,
            suggested_price=validation.pricing.suggested_price,
            gross_profit=validation.pricing.gross_profit,
            gross_margin=validation.pricing.gross_margin,
            minimum_gross_margin_requirement=request.minimum_gross_margin,
            # Unstated budget anchors on the suggested price, keeping the
            # hotel-side limits meaningful without inventing a traveller cap.
            visitor_budget_limit=request.visitor_budget or (validation.pricing.suggested_price + Decimal("200")),
            price_anchor=request.preferred_price or validation.pricing.suggested_price,
            bottleneck_resource=validation.capacity.bottleneck_resource,
            marketing_title=output.marketing_title,
            marketing_content=output.marketing_content,
            marketing_assets=self._marketing_assets(output.marketing_assets, product_name=output.product_name, theme=output.theme, target_crowd=request.target_crowd, weather=request.weather, target_date=request.target_date, price=validation.pricing.suggested_price, room=room, resources=resource_rows, variant_index=variant_index),
            recommendation_reason=" ".join([str(output.recommendation_reason or "").strip(), *compatibility_notes]).strip(),
            risk_message=" ".join([str(output.risk_message or "").strip(), *compatibility_notes]).strip(),
            status=initial_status,
            resources=resource_rows,
            experience_notes={"stay_room_inventory_ids": [int(item.id) for item in stay_rooms[1:]]},
        )
        self.db.add(product)
        self.db.flush()
        return product, validation.as_dict(), agent_result.trace_id, agent_result.fallback_used

    def resolve_intelligence(self, request: GenerateProductRequest, *, natural_language: str = "") -> tuple[GenerateProductRequest, dict[str, Any]]:
        """Resolve factual context once before a multi-variant Agent task.

        Forecast and knowledge failures never become invented facts: callers get
        a visible `VERIFY_REQUIRED` marker and a neutral compatibility tag.
        """
        weather = WeatherService(self.db).get_forecast("杭州", request.target_date)
        scenario = str(weather.get("scenario") or "CLOUDY") if weather.get("usable") else (request.weather or "CLOUDY")
        resolved = request.model_copy(update={"weather": scenario})
        insights = OperationsInsightService(self.db, self.hotel_id).snapshot(target_date=request.target_date)
        knowledge_query = " ".join(part for part in (natural_language, request.theme, request.target_crowd) if part)
        knowledge = KnowledgeService(self.db).search(knowledge_query, target_crowd=request.target_crowd, weather=scenario)
        planning_context = KnowledgeService(self.db).planning_context()
        context = {
            "weather": weather,
            "insights": insights,
            "knowledge": knowledge,
            "tourism_planning_context": planning_context,
        }
        self.intelligence_context = context
        return resolved, context

    def generate_many(
        self,
        request: GenerateProductRequest,
        *,
        initial_status: str = "DRAFT",
        natural_language: str = "",
        resolve_intelligence: bool = True,
    ) -> list[tuple[TravelProduct, dict[str, Any], str, bool]]:
        """Generate several creative candidates over the same real inventory snapshot.

        Each candidate is independently validated and persisted as a draft. The
        business numbers remain deterministic and identical when the resource
        selections are identical; only the creative packaging varies.
        """
        resolved_request = request
        if resolve_intelligence:
            resolved_request, _ = self.resolve_intelligence(request, natural_language=natural_language)
        return [self.generate(resolved_request, variant_index=index, initial_status=initial_status) for index in range(resolved_request.variant_count)]

    def _marketing_payload(self, product: TravelProduct, creative_direction: str = "", *, style: str = "SEEDING") -> dict[str, Any]:
        room = self.db.get(RoomInventory, product.room_inventory_id)
        selections = [{"resource_type": row.resource_type, "resource_id": row.resource_id, "quantity_per_package": row.quantity_per_package} for row in product.resources if row.resource_type != "ROOM"]
        request = GenerateProductRequest(
            target_date=product.target_date,
            weather=product.weather,
            target_crowd=product.target_crowd,
            party_size=product.party_size,
            theme=product.theme,
            room_inventory_id=product.room_inventory_id,
            resource_selections=selections,
            preferred_price=product.price_anchor,
            visitor_budget=product.visitor_budget_limit,
            minimum_gross_margin=product.minimum_gross_margin_requirement,
            variant_count=1,
            creative_direction=marketing_style_direction(style, creative_direction),
        )
        return self._payload(request, room, selections)

    def regenerate_marketing(self, product: TravelProduct, creative_direction: str = "", *, style: str = "SEEDING", generate_image: bool = False) -> tuple[str, bool]:
        # Keep accepting the legacy parameter; this refresh now updates copy only.
        # Marketing refresh is a dedicated Skill, not a re-run of product
        # generation: stayscape-marketing-writer rewrites only the creative
        # packaging, and never touches recommendation_reason / risk_message
        # (those stay product-level and are set once at generation time).
        result = self.orchestrator.generate_marketing(self._marketing_payload(product, creative_direction, style=style))
        output: MarketingAgentOutput = result.value  # type: ignore[assignment]
        room = self.db.get(RoomInventory, product.room_inventory_id)
        if room is None:
            raise AppError("ROOM_NOT_FOUND", "产品关联客房不存在，无法重新生成营销素材")
        product.marketing_title = output.marketing_title
        product.marketing_content = output.marketing_content
        product.marketing_assets = self._marketing_assets(output.marketing_assets, product_name=product.product_name, theme=product.theme, target_crowd=product.target_crowd, weather=product.weather, target_date=product.target_date, price=product.suggested_price, room=room, resources=list(product.resources), variant_index=0, copy_style=style)
        self.db.flush()
        return result.trace_id, result.fallback_used

    def _validate_service(self, service: HotelService, request: GenerateProductRequest, quantity: int) -> None:
        if quantity <= 0:
            raise AppError("VALIDATION_ERROR", "每套服务消耗量必须大于0", field=f"service_{service.id}")
        if not request.target_date <= service.available_date <= _trip_last_date(request) or service.status != "AVAILABLE" or service.available_quantity <= 0:
            raise AppError("HOTEL_SERVICE_UNAVAILABLE", f"酒店服务{service.service_name}当前不可用", field="resource_selections", retryable=True)
        validate_interval(service.start_time, service.end_time, service.service_name)

    def _validate_partner(self, partner: PartnerResource, request: GenerateProductRequest, quantity: int) -> None:
        if quantity <= 0:
            raise AppError("VALIDATION_ERROR", "每套体验消耗量必须大于0", field=f"resource_{partner.id}")
        merchant = partner.merchant
        if not merchant or not resource_is_usable(merchant_status=merchant.cooperation_status, package_enabled=partner.package_enabled, resource_status=partner.status, capacity=partner.remaining_capacity, source_type=partner.source_type):
            raise AppError("PARTNER_RESOURCE_UNAVAILABLE", f"合作资源{partner.resource_name}当前不可组包", field="resource_selections", retryable=True)
        if not request.target_date <= partner.available_date <= _trip_last_date(request):
            raise AppError("DATE_NOT_MATCHED", "合作体验日期不在本次旅程内", field="target_date", retryable=True)
        validate_interval(partner.start_time, partner.end_time, partner.resource_name)

    def recalculate_for_event(self, event: ResourceChangeEvent) -> list[dict[str, Any]]:
        references: list[TravelProduct] = []
        if event.resource_type == "PARTNER_RESOURCE":
            references = [item for item in products_referencing(self.db, "PARTNER_RESOURCE", event.resource_id) if item.hotel_id == self.hotel_id]
        elif event.resource_type == "HOTEL_SERVICE":
            references = [item for item in products_referencing(self.db, "HOTEL_SERVICE", event.resource_id) if item.hotel_id == self.hotel_id]
        elif event.resource_type == "ROOM":
            references = list(self.db.scalars(select(TravelProduct).options(selectinload(TravelProduct.resources), selectinload(TravelProduct.adjustments)).where(TravelProduct.room_inventory_id == event.resource_id, TravelProduct.hotel_id == self.hotel_id)).unique().all())
            room_ids = {int(event.resource_id)}
            candidates = list(self.db.scalars(select(TravelProduct).options(selectinload(TravelProduct.resources), selectinload(TravelProduct.adjustments)).where(TravelProduct.hotel_id == self.hotel_id)).unique().all())
            for candidate in candidates:
                notes = candidate.experience_notes if isinstance(candidate.experience_notes, dict) else {}
                extras = {int(value) for value in notes.get("stay_room_inventory_ids", []) if str(value).isdigit()}
                if extras & room_ids and all(int(item.id) != int(candidate.id) for item in references):
                    references.append(candidate)
        results = []
        for product in references:
            result = self.recalculate_product(product, event)
            results.append(result)
        event.processed = True
        results.extend(reconcile_published_capacity(self.db, self.hotel_id, event=event))
        event.processing_result = {"affectedProducts": json_safe(results)}
        return results

    def recalculate_product(self, product: TravelProduct, event: ResourceChangeEvent | None = None) -> dict[str, Any]:
        old_quantity = product.sale_quantity
        old_price = product.suggested_price
        replacement_id = None
        replacement_message = ""
        room = self.db.get(RoomInventory, product.room_inventory_id)
        if room and room.available_date != product.target_date:
            product.sale_quantity = 0
            product.status = "PAUSED"
            return self._record_adjustment(product, event, old_quantity, old_price, "PAUSE_PRODUCT", "关联客房日期已变化，与产品入住日期不一致", replacement_id)
        if not room:
            product.sale_quantity = 0
            product.status = "PAUSED"
            action = "PAUSE_PRODUCT"
            reason = "关联客房已不存在"
            return self._record_adjustment(product, event, old_quantity, old_price, action, reason, replacement_id)
        rows = list(product.resources)
        experience_notes = product.experience_notes if isinstance(product.experience_notes, dict) else {}
        extra_ids = [int(value) for value in experience_notes.get("stay_room_inventory_ids", []) if str(value).isdigit()]
        required_nights = max(1, int(product.nights or 1))
        stay_rooms = [room]
        expected_room_dates = [product.target_date + timedelta(days=offset) for offset in range(required_nights)]
        for offset, night_date in enumerate(expected_room_dates[1:], start=1):
            extra_room = self.db.get(RoomInventory, extra_ids[offset - 1]) if offset - 1 < len(extra_ids) else None
            if (
                extra_room is None
                or extra_room.hotel_id != self.hotel_id
                or extra_room.room_type != room.room_type
                or extra_room.available_date != night_date
                or extra_room.status != "AVAILABLE"
                or int(extra_room.available_count or 0) <= 0
            ):
                product.sale_quantity = 0
                product.status = "PAUSED"
                return self._record_adjustment(product, event, old_quantity, old_price, "PAUSE_PRODUCT", f"{room.room_type} 在 {night_date.isoformat()} 的住宿库存不可用，已暂停销售", replacement_id)
            stay_rooms.append(extra_room)
        capacity_inputs = [CapacityInput(f"{item.room_type} · {item.available_date}", item.available_count, 1) for item in stay_rooms]
        unit_cost = sum((Decimal(str(item.accounting_cost or 0)) for item in stay_rooms), Decimal("0"))
        invalid_reason = None
        partner_row = None
        schedule_slots: list[tuple[date, time | None, time | None, str]] = []
        scheduled_partners: list[PartnerResource] = []
        for row in rows:
            if row.resource_type == "ROOM":
                continue
            if row.resource_type == "HOTEL_SERVICE":
                service = self.db.get(HotelService, row.resource_id)
                if not service or not product.target_date <= service.available_date <= product.target_date + timedelta(days=max(1, int(product.nights or 1))) or service.status != "AVAILABLE" or service.available_quantity <= 0:
                    invalid_reason = f"酒店服务{row.resource_name}不可用"
                    break
                if service.start_time and service.end_time and service.start_time >= service.end_time:
                    invalid_reason = f"酒店服务{row.resource_name}时间无效"
                    break
                if blocks_schedule(service) and any(day == service.available_date and intervals_overlap(service.start_time, service.end_time, start, end) for day, start, end, _ in schedule_slots):
                    invalid_reason = f"酒店服务{row.resource_name}与套餐内其他活动时间冲突"
                    break
                capacity_inputs.append(CapacityInput(service.service_name, service.available_quantity, row.quantity_per_package))
                unit_cost += service.unit_cost * row.quantity_per_package
                row.unit_cost = service.unit_cost
                if blocks_schedule(service):
                    schedule_slots.append((service.available_date, service.start_time, service.end_time, service.service_name))
            elif row.resource_type == "PARTNER_RESOURCE":
                partner_row = row
                partner = self.db.get(PartnerResource, row.resource_id)
                merchant = self.db.get(Merchant, partner.merchant_id) if partner else None
                if not partner or not merchant or not product.target_date <= partner.available_date <= product.target_date + timedelta(days=max(1, int(product.nights or 1))) or not resource_is_usable(merchant_status=merchant.cooperation_status, package_enabled=partner.package_enabled, resource_status=partner.status, capacity=partner.remaining_capacity, source_type=partner.source_type):
                    replacement = self._find_replacement(product, row, room, capacity_inputs, unit_cost)
                    if replacement:
                        replacement_id = replacement.id
                        row.resource_id = replacement.id
                        row.resource_name = replacement.resource_name
                        row.unit_cost = replacement.settlement_price
                        partner = replacement
                        merchant = replacement.merchant
                        replacement_message = f"已用{replacement.resource_name}替代原体验"
                    else:
                        invalid_reason = f"{row.resource_name}不可用且没有满足约束的替代资源"
                        break
                if not partner:
                    invalid_reason = "合作资源不可用"
                    break
                if not product.target_date <= partner.available_date <= product.target_date + timedelta(days=max(1, int(product.nights or 1))):
                    invalid_reason = f"{partner.resource_name}日期与产品入住日期不一致"
                    break
                if any(day == partner.available_date and intervals_overlap(partner.start_time, partner.end_time, start, end) for day, start, end, _ in schedule_slots):
                    replacement = self._find_replacement(product, row, room, capacity_inputs, unit_cost)
                    if replacement and not any(day == replacement.available_date and intervals_overlap(replacement.start_time, replacement.end_time, start, end) for day, start, end, _ in schedule_slots):
                        replacement_id = replacement.id
                        row.resource_id = replacement.id
                        row.resource_name = replacement.resource_name
                        row.unit_cost = replacement.settlement_price
                        partner = replacement
                    else:
                        invalid_reason = f"{partner.resource_name}与套餐内其他活动时间冲突且没有替代资源"
                        break
                capacity_inputs.append(CapacityInput(partner.resource_name, partner.remaining_capacity, row.quantity_per_package))
                unit_cost += partner.settlement_price * row.quantity_per_package
                schedule_slots.append((partner.available_date, partner.start_time, partner.end_time, partner.resource_name))
                scheduled_partners.append(partner)
        if not invalid_reason:
            invalid_reason = _partner_transfer_issue(scheduled_partners)
        if not invalid_reason:
            counts: dict[tuple[date, str], int] = {}
            for partner in scheduled_partners:
                part, cap = _partner_daypart(partner)
                key = (partner.available_date, part)
                counts[key] = counts.get(key, 0) + 1
                if counts[key] > cap:
                    invalid_reason = f"{partner.available_date.isoformat()} 的{part}时段超过安排上限"
                    break
        if invalid_reason:
            product.sale_quantity = 0
            product.status = "PAUSED"
            reason = invalid_reason
            if replacement_message:
                reason = replacement_message
            return self._record_adjustment(product, event, old_quantity, old_price, "PAUSE_PRODUCT", reason, replacement_id)
        try:
            validation = validate_package(
                capacity_inputs=capacity_inputs,
                unit_cost=unit_cost,
                room_minimum_price=sum((Decimal(str(item.minimum_price or 0)) for item in stay_rooms), Decimal("0")),
                minimum_gross_margin=product.minimum_gross_margin_requirement,
                visitor_budget=product.visitor_budget_limit,
                preferred_price=product.price_anchor,
            )
        except AppError as exc:
            product.sale_quantity = 0
            product.status = "PAUSED"
            return self._record_adjustment(product, event, old_quantity, old_price, "PAUSE_PRODUCT", exc.message, replacement_id)
        # A resource change may reduce what can be sold today, but it must not
        # overwrite the merchant's original listing ceiling.  When a temporary
        # hold later expires, the capacity reconciler can safely restore this
        # ceiling (subject to all real source rows).
        # 这里只按「这套套餐自己的资源」算一次上限，不能因此把数量抬高：
        # 同一房型的所有套餐共享真实库存，最终配额由 reconcile_published_capacity
        # 统一分配。否则会出现「3 套 → 4 套」这种先涨后被压回去的噪音记录。
        ceiling = min(max(0, product.listed_quantity), validation.capacity.sale_quantity)
        if product.status in ACTIVE_PRODUCT_STATUSES:
            product.sale_quantity = min(ceiling, max(0, old_quantity))
        else:
            # 草稿 / 待确认候选不占用在售配额，直接跟随资源变化（房量恢复时也能涨回来）。
            product.sale_quantity = ceiling
        product.unit_cost = validation.pricing.unit_cost
        product.minimum_allowed_price = validation.pricing.minimum_allowed_price
        product.suggested_price = validation.pricing.suggested_price
        product.gross_profit = validation.pricing.gross_profit
        product.gross_margin = validation.pricing.gross_margin
        product.bottleneck_resource = validation.capacity.bottleneck_resource
        if product.sale_quantity <= 0:
            product.status = "SOLD_OUT"
        elif product.status == "PAUSED" or product.status == "SOLD_OUT":
            product.status = "LOW_STOCK" if product.sale_quantity <= 2 else "ON_SALE"
        elif product.status == "ON_SALE" or product.status == "LOW_STOCK":
            product.status = "LOW_STOCK" if product.sale_quantity <= 2 else "ON_SALE"
        action = "REPLACE_RESOURCE" if replacement_id else ("UPDATE_QUANTITY" if product.sale_quantity != old_quantity else ("REPRICE" if product.suggested_price != old_price else "UPDATE_QUANTITY"))
        if product.sale_quantity != old_quantity:
            reason = replacement_message or f"资源变化后重新计算：{old_quantity} 套 → {product.sale_quantity} 套"
        elif Decimal(product.suggested_price) != Decimal(old_price):
            reason = f"资源变化后按新成本改价：¥{old_price} → ¥{product.suggested_price}（数量保持 {product.sale_quantity} 套）"
        else:
            reason = replacement_message or f"资源变化后重新校验通过，数量保持 {product.sale_quantity} 套"
        return self._record_adjustment(product, event, old_quantity, old_price, action, reason, replacement_id)

    def _find_replacement(self, product: TravelProduct, row: ProductResource, room: RoomInventory, existing_capacity: list[CapacityInput], existing_cost: Decimal) -> PartnerResource | None:
        old = self.db.get(PartnerResource, row.resource_id)
        if not old:
            return None
        candidates = list(self.db.scalars(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(Merchant.hotel_id == self.hotel_id, PartnerResource.id != old.id, PartnerResource.available_date == old.available_date, PartnerResource.category == old.category, PartnerResource.package_enabled.is_(True), PartnerResource.status == "AVAILABLE", PartnerResource.source_type.in_(["PARTNER", "DEMO"]), Merchant.cooperation_status == "ACTIVE").order_by(PartnerResource.settlement_price)).unique().all())
        for candidate in candidates:
            if candidate.remaining_capacity < row.quantity_per_package:
                continue
            if not crowd_supported(candidate.suitable_crowds, product.target_crowd, minimum_age=candidate.minimum_age, maximum_age=candidate.maximum_age):
                continue
            if not is_weather_supported(candidate.weather_tags, product.weather):
                continue
            if any(
                intervals_overlap(candidate.start_time, candidate.end_time, source.start_time, source.end_time)
                for source in [self.db.get(HotelService, existing.resource_id) if existing.resource_type == "HOTEL_SERVICE" else self.db.get(PartnerResource, existing.resource_id) for existing in product.resources if existing.id != row.id and existing.resource_type in {"HOTEL_SERVICE", "PARTNER_RESOURCE"}]
                if source is not None and getattr(source, "available_date", None) == candidate.available_date and (not isinstance(source, HotelService) or blocks_schedule(source))
            ):
                continue
            try:
                validate_interval(candidate.start_time, candidate.end_time, candidate.resource_name)
                validate = validate_package(
                    capacity_inputs=existing_capacity + [CapacityInput(candidate.resource_name, candidate.remaining_capacity, row.quantity_per_package)],
                    unit_cost=existing_cost + candidate.settlement_price * row.quantity_per_package,
                    room_minimum_price=room.minimum_price,
                    minimum_gross_margin=product.minimum_gross_margin_requirement,
                    visitor_budget=product.visitor_budget_limit,
                    preferred_price=product.price_anchor,
                )
                if validate.capacity.sale_quantity > 0:
                    return candidate
            except AppError:
                continue
        return None

    def _record_adjustment(self, product: TravelProduct, event: ResourceChangeEvent | None, old_quantity: int, old_price: Decimal, action: str, reason: str, replacement_id: int | None) -> dict[str, Any]:
        # 数量、价格、替代资源都没变就不要写「调整记录」，
        # 否则动态运营里会出现大量「6 套 → 6 套」的无意义条目。
        if replacement_id is None and int(old_quantity) == int(product.sale_quantity) and Decimal(old_price) == Decimal(product.suggested_price):
            return {"product_id": product.id, "product_name": product.product_name, "old_quantity": old_quantity, "new_quantity": product.sale_quantity, "old_price": old_price, "new_price": product.suggested_price, "action": action, "bottleneck_resource": product.bottleneck_resource, "status": product.status, "replacement_resource_id": replacement_id, "reason": reason}
        record = ProductAdjustmentRecord(product_id=product.id, change_event_id=event.id if event else None, old_quantity=old_quantity, new_quantity=product.sale_quantity, old_price=old_price, new_price=product.suggested_price, action=action, replacement_resource_id=replacement_id, reason=reason)
        self.db.add(record)
        self.db.flush()
        return {"product_id": product.id, "product_name": product.product_name, "old_quantity": old_quantity, "new_quantity": product.sale_quantity, "old_price": old_price, "new_price": product.suggested_price, "action": action, "bottleneck_resource": product.bottleneck_resource, "status": product.status, "replacement_resource_id": replacement_id, "reason": reason}
