"""Editable multi-day visitor plans backed by the physical inventory tables.

Published products are merchant-reviewed one-click offers.  This service is
the complementary visitor journey: it makes a draft from natural-language
preferences, lets the visitor remove/reorder real rows, then holds the exact
rows atomically.  It intentionally never treats an LLM suggestion as stock.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..core.exceptions import AppError
from ..models import HotelService, Merchant, PartnerResource, RoomInventory, VisitorTripPlan
from ..rules.availability_rule import resource_is_usable
from ..rules.crowd_rule import crowd_supported
from ..rules.time_rule import intervals_overlap
from ..rules.weather_rule import is_weather_supported
from ..schemas.trip_plans import TripPlanItemInput, TripPlanRequest
from .inventory_service import reconcile_published_capacity


NON_EXCLUSIVE_SERVICE_TYPES = {"BREAKFAST", "PARKING", "LUGGAGE_STORAGE", "LATE_CHECKOUT"}
ACTIVE_PLAN_STATUSES = {"HELD", "CONFIRMED"}
_DAY_NUMBERS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


@dataclass
class _PreparedPlan:
    itinerary: list[dict[str, Any]]
    total_price: Decimal
    allocations: list[tuple[str, int, int, Any]]


def _available(source: Any) -> int:
    if isinstance(source, RoomInventory):
        return max(0, int(source.available_count))
    if isinstance(source, HotelService):
        return max(0, int(source.available_quantity))
    if isinstance(source, PartnerResource):
        return max(0, int(source.remaining_capacity))
    return 0


def _set_available(source: Any, value: int) -> None:
    if isinstance(source, RoomInventory):
        source.available_count = max(0, value)
    elif isinstance(source, HotelService):
        source.available_quantity = max(0, value)
    elif isinstance(source, PartnerResource):
        source.remaining_capacity = max(0, value)


def _name(source: Any) -> str:
    return str(getattr(source, "room_type", "") or getattr(source, "service_name", "") or getattr(source, "resource_name", "") or "资源")


def _date(source: Any) -> date:
    return source.available_date


def _type_price(source: Any) -> Decimal:
    if isinstance(source, RoomInventory):
        return Decimal(source.normal_price)
    if isinstance(source, HotelService):
        return Decimal(source.reference_price)
    return Decimal(source.market_price)


def _non_exclusive(source: Any) -> bool:
    return isinstance(source, HotelService) and source.service_type in NON_EXCLUSIVE_SERVICE_TYPES


def _time_sort(source: Any) -> time:
    if isinstance(source, RoomInventory):
        return time(15, 0)
    return getattr(source, "start_time", None) or time(23, 59)


class TripPlanService:
    def __init__(self, db: Session, hotel_id: int) -> None:
        self.db = db
        self.hotel_id = hotel_id
        # Routes use this to notify the hotel workbench about every published
        # product whose remaining quantity changed because of a custom hold.
        self.last_capacity_adjustments: list[dict[str, Any]] = []

    def _load_source(self, resource_type: str, resource_id: int, *, lock: bool = False):
        if resource_type == "ROOM":
            query = select(RoomInventory).where(RoomInventory.id == resource_id, RoomInventory.hotel_id == self.hotel_id)
        elif resource_type == "HOTEL_SERVICE":
            query = select(HotelService).where(HotelService.id == resource_id, HotelService.hotel_id == self.hotel_id)
        elif resource_type == "PARTNER_RESOURCE":
            query = (
                select(PartnerResource)
                .join(Merchant)
                .options(selectinload(PartnerResource.merchant))
                .where(PartnerResource.id == resource_id, Merchant.hotel_id == self.hotel_id)
            )
        else:
            return None
        return self.db.scalar(query.with_for_update() if lock else query)

    def _validate_source(self, source: Any, resource_type: str, request: TripPlanRequest, quantity: int) -> None:
        if source is None:
            raise AppError("TRIP_RESOURCE_NOT_FOUND", "行程中的资源不存在或不属于当前酒店", field="items", retryable=True)
        if quantity <= 0:
            raise AppError("VALIDATION_ERROR", "行程资源数量必须大于 0", field="items")
        end_date = request.start_date + timedelta(days=request.duration_days - 1)
        if not (request.start_date <= _date(source) <= end_date):
            raise AppError("TRIP_DATE_NOT_AVAILABLE", f"{_name(source)} 不在本次行程日期内", field="items", retryable=True)
        if isinstance(source, RoomInventory):
            if source.status in {"DISABLED", "SOLD_OUT"} or source.max_guests < request.party_size:
                raise AppError("ROOM_INVENTORY_INSUFFICIENT", f"{_name(source)} 不适合当前同行人数", field="items", retryable=True)
        elif isinstance(source, HotelService):
            if source.status != "AVAILABLE" or not crowd_supported(source.suitable_crowds, request.target_crowd):
                raise AppError("HOTEL_SERVICE_UNAVAILABLE", f"{_name(source)} 当前不可用", field="items", retryable=True)
        elif isinstance(source, PartnerResource):
            merchant = source.merchant
            if not resource_is_usable(
                merchant_status=merchant.cooperation_status if merchant else "TERMINATED",
                package_enabled=source.package_enabled,
                resource_status=source.status,
                capacity=source.remaining_capacity,
                source_type=source.source_type,
            ):
                raise AppError("PARTNER_RESOURCE_UNAVAILABLE", f"{_name(source)} 当前不可预约", field="items", retryable=True)
            if not crowd_supported(source.suitable_crowds, request.target_crowd, minimum_age=source.minimum_age, maximum_age=source.maximum_age):
                raise AppError("CROWD_NOT_SUPPORTED", f"{_name(source)} 不适合当前出行人群", field="items", retryable=True)
            if not is_weather_supported(source.weather_tags, request.weather):
                raise AppError("WEATHER_NOT_SUPPORTED", f"{_name(source)} 暂不适合当前出行条件", field="items", retryable=True)

    def _item_dict(self, source: Any, resource_type: str, quantity: int, *, sort_order: int = 0) -> dict[str, Any]:
        source_date = _date(source)
        day = (source_date - self._request_start_date).days + 1
        unit_price = _type_price(source)
        availability = _available(source)
        start = None if isinstance(source, RoomInventory) else getattr(source, "start_time", None)
        end = None if isinstance(source, RoomInventory) else getattr(source, "end_time", None)
        if isinstance(source, RoomInventory):
            description = source.features
            address = "酒店"
        elif isinstance(source, HotelService):
            description = "到店后按酒店确认方式使用"
            address = "酒店内"
        else:
            description = source.description
            address = source.address
        return {
            "day": day,
            "date": source_date.isoformat(),
            "sort_order": sort_order,
            "resource_type": resource_type,
            "resource_id": source.id,
            "resource_name": _name(source),
            "quantity": quantity,
            "start_time": start.strftime("%H:%M") if start else None,
            "end_time": end.strftime("%H:%M") if end else None,
            "address": address,
            "description": description,
            "image_url": str(getattr(source, "image_url", "") or ""),
            "image_source": str(getattr(source, "image_source", "") or ""),
            "image_attribution": str(getattr(source, "image_attribution", "") or ""),
            "unit_price": str(unit_price.quantize(Decimal("0.01"))),
            "subtotal": str((unit_price * quantity).quantize(Decimal("0.01"))),
            "available_quantity": availability,
            "low_stock": availability <= max(3, quantity * 2),
            "category": getattr(source, "category", None) or getattr(source, "service_type", None) or "住宿",
        }

    def _prepare(
        self,
        request: TripPlanRequest,
        items: Iterable[TripPlanItemInput],
        *,
        lock: bool = False,
        credits: dict[tuple[str, int], int] | None = None,
    ) -> _PreparedPlan:
        self._request_start_date = request.start_date
        loaded: list[tuple[TripPlanItemInput, Any]] = []
        requirements: dict[tuple[str, int], tuple[int, Any]] = {}
        for item in items:
            source = self._load_source(item.resource_type, item.resource_id, lock=lock)
            self._validate_source(source, item.resource_type, request, item.quantity)
            key = (item.resource_type, item.resource_id)
            quantity = (requirements.get(key, (0, source))[0] if key in requirements else 0) + item.quantity
            requirements[key] = (quantity, source)
            loaded.append((item, source))

        for (resource_type, resource_id), (quantity, source) in requirements.items():
            effective_available = _available(source) + int((credits or {}).get((resource_type, resource_id), 0))
            if effective_available < quantity:
                raise AppError(
                    "INVENTORY_INSUFFICIENT",
                    f"{_name(source)} 仅剩 {effective_available} 个可用名额，请替换或减少数量",
                    field="items",
                    retryable=True,
                    details={"resource_type": resource_type, "resource_id": resource_id, "available": effective_available, "required": quantity},
                )

        rooms_by_date: dict[date, int] = defaultdict(int)
        slots: dict[date, list[tuple[time | None, time | None, str]]] = defaultdict(list)
        itinerary: list[dict[str, Any]] = []
        total = Decimal("0")
        for item, source in loaded:
            if item.resource_type == "ROOM":
                rooms_by_date[_date(source)] += item.quantity
            if not _non_exclusive(source):
                current = slots[_date(source)]
                start = None if isinstance(source, RoomInventory) else getattr(source, "start_time", None)
                end = None if isinstance(source, RoomInventory) else getattr(source, "end_time", None)
                if start and end and any(intervals_overlap(start, end, other_start, other_end) for other_start, other_end, _ in current):
                    raise AppError("TIME_CONFLICT", f"{_name(source)} 与同一天的其他活动时间冲突，请拖动、替换或删除其中一项", field="items", retryable=True)
                current.append((start, end, _name(source)))
            itinerary.append(self._item_dict(source, item.resource_type, item.quantity, sort_order=item.sort_order))
            total += _type_price(source) * item.quantity

        expected_dates = [request.start_date + timedelta(days=offset) for offset in range(request.duration_days)]
        missing_room_dates = [value.isoformat() for value in expected_dates if rooms_by_date[value] < 1]
        if missing_room_dates:
            raise AppError("TRIP_ROOM_REQUIRED", "每个入住日都需要保留一个可用房型", field="items", retryable=True, details={"missing_dates": missing_room_dates})
        itinerary.sort(key=lambda item: (item["date"], item["sort_order"], item["start_time"] or "15:00", item["resource_name"]))
        allocations = [(resource_type, resource_id, quantity, source) for (resource_type, resource_id), (quantity, source) in requirements.items()]
        return _PreparedPlan(itinerary=itinerary, total_price=total.quantize(Decimal("0.01")), allocations=allocations)

    @staticmethod
    def _preference_categories(text: str) -> set[str]:
        lowered = text.lower()
        aliases = {
            "THEME_PARK": ("乐园", "游乐", "主题公园"),
            "CULTURE": ("博物馆", "看展", "非遗", "手作", "文化", "良渚"),
            "SPORT": ("运动", "攀岩", "卡丁车", "骑行", "射箭"),
            "FOOD": ("美食", "咖啡", "甜品", "杭帮菜"),
            "NATURE": ("自然", "湿地", "动物", "植物"),
            "NIGHTLIFE": ("夜游", "夜景", "夜场", "音乐"),
            "PHOTO": ("拍照", "旅拍", "摄影"),
            "PERFORMANCE": ("演出", "剧场", "儿童剧"),
            "KIDS": ("亲子", "儿童", "孩子", "科学", "乐园"),
            "CITY_WALK": ("西湖", "漫游", "散步", "街区", "city walk"),
            "ENTERTAINMENT": ("陶艺", "音乐现场", "娱乐"),
        }
        return {category for category, words in aliases.items() if any(word in lowered for word in words)}

    @classmethod
    def _ordered_preference_categories(cls, text: str) -> list[str]:
        """Keep the visitor's written order for "day one / day two" wishes."""
        lowered = text.lower()
        aliases = {
            "THEME_PARK": ("主题公园", "游乐园", "乐园"),
            "CULTURE": ("博物馆", "看展", "非遗", "手作", "文化", "良渚"),
            "SPORT": ("攀岩", "卡丁车", "骑行", "射箭", "运动"),
            "FOOD": ("美食", "杭帮菜", "咖啡", "甜品", "吃饭"),
            "NATURE": ("湿地", "动物", "植物", "自然"),
            "NIGHTLIFE": ("夜游", "夜景", "夜场", "夜晚"),
            "PHOTO": ("旅拍", "摄影", "拍照"),
            "PERFORMANCE": ("演出", "剧场", "儿童剧"),
            "KIDS": ("亲子", "儿童", "孩子", "科学"),
            "CITY_WALK": ("西湖", "漫游", "散步", "街区"),
            "ENTERTAINMENT": ("陶艺", "音乐现场", "娱乐"),
        }
        positioned: list[tuple[int, str]] = []
        for category, words in aliases.items():
            positions = [lowered.find(word) for word in words if lowered.find(word) >= 0]
            if positions:
                positioned.append((min(positions), category))
        return [category for _, category in sorted(positioned)]

    @classmethod
    def _day_sections(cls, text: str, duration_days: int) -> dict[int, str]:
        """Split explicit day clauses without losing the visitor's actual nouns."""
        pattern = re.compile(r"(?:第?\s*([一二三四五六七八九十\d]+)\s*(?:天|日)|day\s*(\d+))", re.IGNORECASE)
        markers = list(pattern.finditer(text))
        sections: dict[int, str] = {}
        for index, marker in enumerate(markers):
            raw = marker.group(1) or marker.group(2) or ""
            number = int(raw) if raw.isdigit() else _DAY_NUMBERS.get(raw, 0)
            if number < 1 or number > duration_days:
                continue
            next_start = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            sections[number - 1] = text[marker.end() : next_start]
        return sections

    @classmethod
    def _day_preferences(cls, text: str, duration_days: int) -> dict[int, list[str]]:
        """Extract compact day-specific wishes such as “第一天看展，第二天西湖”."""
        return {
            day_index: ordered
            for day_index, section in cls._day_sections(text, duration_days).items()
            if (ordered := cls._ordered_preference_categories(section))
        }

    @staticmethod
    def _literal_preference_terms(text: str) -> list[str]:
        """Preserve concrete places/activities instead of reducing all of them to a category.

        A visitor asking for a museum should not receive a generic craft class
        merely because both belong to CULTURE.  These terms remain a ranking
        signal rather than a hard requirement, so an unavailable venue still
        gives a useful alternative.
        """
        lowered = text.lower()
        terms = (
            "博物馆", "良渚", "西湖", "运河", "乐园", "湿地", "动物", "植物",
            "攀岩", "卡丁车", "射箭", "骑行", "演出", "剧场", "旅拍", "摄影",
            "咖啡", "甜品", "杭帮菜", "夜市", "陶艺", "手作",
        )
        return [term for term in terms if term in lowered]

    @staticmethod
    def _matches_literal_terms(partner: PartnerResource, terms: list[str]) -> bool:
        if not terms:
            return False
        searchable = " ".join(
            str(value or "")
            for value in (partner.resource_name, partner.description, partner.address)
        ).lower()
        return any(term.lower() in searchable for term in terms)

    @staticmethod
    def _matches_categories(partner: PartnerResource, categories: list[str] | set[str]) -> bool:
        wanted = {item.upper() for item in categories}
        if str(partner.category).upper() in wanted:
            return True
        semantic = TripPlanService._preference_categories(
            f"{partner.resource_name} {partner.description} {partner.address}"
        )
        return bool(semantic & wanted)

    @staticmethod
    def _overlaps(candidate: PartnerResource, selected: list[PartnerResource]) -> bool:
        return any(
            intervals_overlap(candidate.start_time, candidate.end_time, item.start_time, item.end_time)
            for item in selected
        )

    def propose(self, request: TripPlanRequest, *, variants: int = 3) -> list[dict[str, Any]]:
        self._request_start_date = request.start_date
        days = [request.start_date + timedelta(days=index) for index in range(request.duration_days)]
        rooms = list(
            self.db.scalars(
                select(RoomInventory).where(
                    RoomInventory.hotel_id == self.hotel_id,
                    RoomInventory.available_date.in_(days),
                    RoomInventory.status == "AVAILABLE",
                    RoomInventory.available_count > 0,
                    RoomInventory.max_guests >= request.party_size,
                )
            ).all()
        )
        services = list(
            self.db.scalars(
                select(HotelService).where(
                    HotelService.hotel_id == self.hotel_id,
                    HotelService.available_date.in_(days),
                    HotelService.status == "AVAILABLE",
                    HotelService.available_quantity > 0,
                )
            ).all()
        )
        partners = list(
            self.db.scalars(
                select(PartnerResource)
                .join(Merchant)
                .options(selectinload(PartnerResource.merchant))
                .where(
                    Merchant.hotel_id == self.hotel_id,
                    PartnerResource.available_date.in_(days),
                    PartnerResource.status == "AVAILABLE",
                    PartnerResource.package_enabled.is_(True),
                    PartnerResource.remaining_capacity >= request.party_size,
                )
            ).unique().all()
        )
        rooms_by_day: dict[date, list[RoomInventory]] = defaultdict(list)
        services_by_day: dict[date, list[HotelService]] = defaultdict(list)
        partners_by_day: dict[date, list[PartnerResource]] = defaultdict(list)
        for room in rooms:
            rooms_by_day[room.available_date].append(room)
        for service in services:
            if crowd_supported(service.suitable_crowds, request.target_crowd):
                services_by_day[service.available_date].append(service)
        for partner in partners:
            if self._partner_matches(partner, request):
                partners_by_day[partner.available_date].append(partner)
        if any(not rooms_by_day[value] for value in days):
            raise AppError("TRIP_ROOM_REQUIRED", "所选日期没有足够房型，请更换日期或缩短行程", field="start_date", retryable=True)

        preferred = self._preference_categories(request.natural_language)
        per_day_preferences = self._day_preferences(request.natural_language, request.duration_days)
        global_literal_terms = self._literal_preference_terms(request.natural_language)
        per_day_literal_terms = {
            day_index: self._literal_preference_terms(section)
            for day_index, section in self._day_sections(request.natural_language, request.duration_days).items()
        }
        options: list[dict[str, Any]] = []
        seen: set[tuple[int, ...]] = set()
        for variant in range(max(1, min(variants, 3))):
            selected: list[TripPlanItemInput] = []
            for day_index, value in enumerate(days):
                day_rooms = sorted(rooms_by_day[value], key=lambda item: (-item.available_count, item.normal_price, item.id))
                selected.append(TripPlanItemInput(resource_type="ROOM", resource_id=day_rooms[(variant + day_index) % len(day_rooms)].id, quantity=1, sort_order=0))
                if request.include_breakfast:
                    breakfast = sorted(
                        [item for item in services_by_day[value] if item.service_type == "BREAKFAST" and item.available_quantity >= request.party_size],
                        key=lambda item: (-item.available_quantity, item.id),
                    )
                    if breakfast:
                        selected.append(TripPlanItemInput(resource_type="HOTEL_SERVICE", resource_id=breakfast[(variant + day_index) % len(breakfast)].id, quantity=request.party_size, sort_order=90))
                day_preferences = per_day_preferences.get(day_index, [])
                candidates = sorted(
                    partners_by_day[value],
                    key=lambda item: (
                        not self._matches_categories(item, day_preferences) if day_preferences else item.category not in preferred,
                        -item.remaining_capacity,
                        item.start_time or time(23, 59),
                        item.id,
                    ),
                )
                # Concrete wording wins over a broad category.  If a day was
                # written explicitly, use that day's nouns; otherwise apply a
                # concise global request such as "想去博物馆".
                literal_terms = per_day_literal_terms.get(day_index, global_literal_terms)
                literal_candidates = [item for item in candidates if self._matches_literal_terms(item, literal_terms)]
                if literal_candidates:
                    candidates = literal_candidates
                if candidates:
                    chosen_for_day: list[PartnerResource] = []
                    # A written "看展再吃饭" should produce two compatible
                    # rows when the inventory has them, rather than discard one
                    # of the explicit wishes.  Keep the first two so the mobile
                    # editor stays focused and can still add alternatives.
                    for preference_index, category in enumerate(day_preferences[:2]):
                        category_candidates = [item for item in candidates if self._matches_categories(item, [category])]
                        if not category_candidates:
                            continue
                        start = (variant + day_index + preference_index) % len(category_candidates)
                        choice = next(
                            (category_candidates[(start + offset) % len(category_candidates)] for offset in range(len(category_candidates)) if category_candidates[(start + offset) % len(category_candidates)] not in chosen_for_day and not self._overlaps(category_candidates[(start + offset) % len(category_candidates)], chosen_for_day)),
                            None,
                        )
                        if choice:
                            chosen_for_day.append(choice)
                    if not chosen_for_day:
                        chosen_for_day.append(candidates[(variant + day_index) % len(candidates)])
                    for slot, chosen in enumerate(chosen_for_day):
                        selected.append(TripPlanItemInput(resource_type="PARTNER_RESOURCE", resource_id=chosen.id, quantity=request.party_size, sort_order=10 + slot * 10))
            signature = tuple(item.resource_id for item in selected if item.resource_type == "PARTNER_RESOURCE")
            if signature in seen:
                continue
            seen.add(signature)
            prepared = self._prepare(request, selected)
            if request.budget and prepared.total_price > request.budget * Decimal("1.25"):
                # Keep a viable option visible instead of inventing a price;
                # its UI can explicitly say it is over the entered budget.
                pass
            options.append(self._draft_dict(request, prepared, status="DRAFT"))
        if not options:
            raise AppError("TRIP_PLAN_NOT_AVAILABLE", "当前日期没有可以组成完整行程的可用组合", retryable=True)
        return options

    def _partner_matches(self, partner: PartnerResource, request: TripPlanRequest) -> bool:
        merchant = partner.merchant
        return bool(
            merchant
            and resource_is_usable(
                merchant_status=merchant.cooperation_status,
                package_enabled=partner.package_enabled,
                resource_status=partner.status,
                capacity=partner.remaining_capacity,
                source_type=partner.source_type,
            )
            and crowd_supported(partner.suitable_crowds, request.target_crowd, minimum_age=partner.minimum_age, maximum_age=partner.maximum_age)
            and is_weather_supported(partner.weather_tags, request.weather)
        )

    def _draft_dict(self, request: TripPlanRequest, prepared: _PreparedPlan, *, status: str, plan_id: int | None = None, reserved_until: datetime | None = None) -> dict[str, Any]:
        return {
            "id": plan_id,
            "plan_name": request.plan_name,
            "natural_language": request.natural_language,
            "start_date": request.start_date.isoformat(),
            "duration_days": request.duration_days,
            "target_crowd": request.target_crowd,
            "party_size": request.party_size,
            "weather": request.weather,
            "budget": str(request.budget) if request.budget is not None else None,
            "total_price": str(prepared.total_price),
            "status": status,
            "reserved_until": reserved_until.isoformat() if reserved_until else None,
            "items": [
                {
                    "resource_type": item["resource_type"],
                    "resource_id": item["resource_id"],
                    "quantity": item["quantity"],
                    "sort_order": item["sort_order"],
                }
                for item in prepared.itinerary
            ],
            "itinerary": prepared.itinerary,
            "low_stock_items": [item for item in prepared.itinerary if item["low_stock"]],
        }

    def hold(self, request: TripPlanRequest, items: list[TripPlanItemInput], *, contact_name: str, contact_phone: str) -> VisitorTripPlan:
        prepared = self._prepare(request, items, lock=True)
        allocations = []
        for resource_type, resource_id, quantity, source in prepared.allocations:
            before = _available(source)
            _set_available(source, before - quantity)
            if _available(source) <= 0:
                source.status = "SOLD_OUT"
            allocations.append({"resource_type": resource_type, "resource_id": resource_id, "resource_name": _name(source), "quantity": quantity, "before": before, "after": _available(source)})
        plan = VisitorTripPlan(
            hotel_id=self.hotel_id,
            source_product_id=request.source_product_id,
            plan_name=request.plan_name,
            natural_language=request.natural_language,
            start_date=request.start_date,
            duration_days=request.duration_days,
            target_crowd=request.target_crowd,
            party_size=request.party_size,
            itinerary=prepared.itinerary,
            total_price=prepared.total_price,
            status="HELD",
            reserved_until=datetime.now(timezone.utc) + timedelta(minutes=settings.visitor_intent_hold_minutes),
            allocation_snapshot={"allocations": allocations, "created_at": datetime.now(timezone.utc).isoformat()},
            contact_name=contact_name,
            contact_phone=contact_phone,
        )
        self.db.add(plan)
        self.db.flush()
        self.last_capacity_adjustments = reconcile_published_capacity(self.db, self.hotel_id)
        return plan

    def release(self, plan: VisitorTripPlan, *, expired: bool = False) -> dict[str, Any]:
        if plan.status not in ACTIVE_PLAN_STATUSES:
            return {"released": False, "reason": "plan_not_held"}
        snapshot = plan.allocation_snapshot or {}
        restored = []
        for allocation in snapshot.get("allocations", []) if isinstance(snapshot, dict) else []:
            source = self._load_source(str(allocation["resource_type"]), int(allocation["resource_id"]), lock=True)
            if source is None:
                continue
            before = _available(source)
            _set_available(source, before + int(allocation.get("quantity", 0)))
            if getattr(source, "status", None) == "SOLD_OUT":
                source.status = "AVAILABLE"
            restored.append({**allocation, "before": before, "after": _available(source)})
        plan.status = "EXPIRED" if expired else "RELEASED"
        plan.released_at = datetime.now(timezone.utc)
        snapshot["restored_allocations"] = restored
        snapshot["released_at"] = plan.released_at.isoformat()
        plan.allocation_snapshot = snapshot
        self.last_capacity_adjustments = reconcile_published_capacity(self.db, self.hotel_id)
        return {"released": True, "restored": restored, "affected_products": self.last_capacity_adjustments}

    def replace(self, plan: VisitorTripPlan, request: TripPlanRequest, items: list[TripPlanItemInput], *, contact_name: str | None = None, contact_phone: str | None = None) -> VisitorTripPlan:
        if plan.status != "HELD":
            raise AppError("TRIP_PLAN_NOT_EDITABLE", "只有暂留中的行程可以继续修改", retryable=True)
        snapshot = plan.allocation_snapshot or {}
        credits: dict[tuple[str, int], int] = defaultdict(int)
        for allocation in snapshot.get("allocations", []) if isinstance(snapshot, dict) else []:
            credits[(str(allocation["resource_type"]), int(allocation["resource_id"]))] += int(allocation.get("quantity", 0))
        prepared = self._prepare(request, items, lock=True, credits=credits)
        # The new selection has already been fully validated against a view
        # that includes this plan's own hold, so no partial release can leak.
        for allocation in snapshot.get("allocations", []) if isinstance(snapshot, dict) else []:
            source = self._load_source(str(allocation["resource_type"]), int(allocation["resource_id"]), lock=True)
            if source:
                _set_available(source, _available(source) + int(allocation.get("quantity", 0)))
                if getattr(source, "status", None) == "SOLD_OUT":
                    source.status = "AVAILABLE"
        new_allocations = []
        for resource_type, resource_id, quantity, source in prepared.allocations:
            before = _available(source)
            _set_available(source, before - quantity)
            if _available(source) <= 0:
                source.status = "SOLD_OUT"
            new_allocations.append({"resource_type": resource_type, "resource_id": resource_id, "resource_name": _name(source), "quantity": quantity, "before": before, "after": _available(source)})
        plan.plan_name = request.plan_name
        plan.natural_language = request.natural_language
        plan.start_date = request.start_date
        plan.duration_days = request.duration_days
        plan.target_crowd = request.target_crowd
        plan.party_size = request.party_size
        plan.source_product_id = request.source_product_id
        plan.itinerary = prepared.itinerary
        plan.total_price = prepared.total_price
        plan.reserved_until = datetime.now(timezone.utc) + timedelta(minutes=settings.visitor_intent_hold_minutes)
        plan.allocation_snapshot = {"allocations": new_allocations, "updated_at": datetime.now(timezone.utc).isoformat()}
        if contact_name:
            plan.contact_name = contact_name
        if contact_phone:
            plan.contact_phone = contact_phone
        self.last_capacity_adjustments = reconcile_published_capacity(self.db, self.hotel_id)
        return plan

    def to_dict(self, plan: VisitorTripPlan) -> dict[str, Any]:
        itinerary = list(plan.itinerary or [])
        return {
            "id": plan.id,
            "plan_name": plan.plan_name,
            "natural_language": plan.natural_language,
            "start_date": plan.start_date.isoformat(),
            "duration_days": plan.duration_days,
            "target_crowd": plan.target_crowd,
            "party_size": plan.party_size,
            "total_price": str(plan.total_price),
            "status": plan.status,
            "reserved_until": plan.reserved_until.isoformat() if plan.reserved_until else None,
            "items": [
                {
                    "resource_type": item["resource_type"],
                    "resource_id": item["resource_id"],
                    "quantity": item["quantity"],
                    "sort_order": item.get("sort_order", 0),
                }
                for item in itinerary
            ],
            "itinerary": itinerary,
            "low_stock_items": [item for item in itinerary if item.get("low_stock")],
        }


def sweep_expired_trip_plans(db: Session, hotel_id: int | None = None) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    query = select(VisitorTripPlan).where(VisitorTripPlan.status == "HELD", VisitorTripPlan.reserved_until.is_not(None), VisitorTripPlan.reserved_until <= now)
    if hotel_id is not None:
        query = query.where(VisitorTripPlan.hotel_id == hotel_id)
    plans = list(db.scalars(query.with_for_update()).all())
    results = []
    for plan in plans:
        results.append(TripPlanService(db, plan.hotel_id).release(plan, expired=True))
    return results
