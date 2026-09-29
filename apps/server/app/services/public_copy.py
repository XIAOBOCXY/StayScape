"""Public-facing travel copy guardrails.

The operator console can contain operational data.  Visitor endpoints use these
helpers so generated text stays warm, useful and free of internal jargon.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from .serializers import product_to_dict
from .knowledge_service import CURATED_HANGZHOU_KNOWLEDGE

# Every visitor product is anchored to a hotel room night, so the shortest
# sellable package is 2 days / 1 night and there is no "day trip" option.
DEFAULT_STAY_NIGHTS = 1
MAX_STAY_NIGHTS = 3
_CHECK_IN_TIME = "15:00"
_CHECK_OUT_TIME = "12:00"
_LATEST_DAY_ONE_MINUTES = 13 * 60

_INTERNAL_LANGUAGE = re.compile(
    r"(?:库存|房量|成本|售价|毛利|规则引擎|容量约束|真实容量|实时余量|固定场次|"
    r"可直接销售|确定性|履约|供给|产品草稿|酒店服务|实时计算|校验|Demo|Mock|"
    r"Skill|Agent|trace[_ -]?id)",
    re.IGNORECASE,
)
_SENTENCES = re.compile(r"[^。！？!?]+[。！？!?]?")
_GENERIC_LANGUAGE = re.compile(
    r"(?:把这段体验慢慢安排进你的杭州行程|把杭州的一段时光留给今天|把这段杭州时光留给周末|"
    r"不用把一天排满|给散步、吃饭和临时发现留一点空白|住进杭州，慢慢体验这座城市的另一面)",
    re.IGNORECASE,
)


def public_travel_copy(value: object, fallback: str = "") -> str:
    """Remove operational sentences from text returned to a traveller."""

    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return fallback
    kept = [
        sentence.strip()
        for sentence in _SENTENCES.findall(text)
        if sentence.strip()
        and not _INTERNAL_LANGUAGE.search(sentence)
        and not _GENERIC_LANGUAGE.search(sentence)
    ]
    result = "".join(kept).strip()
    return result if len(result) >= 6 else fallback


def _room_package_quantity(product: Any) -> int:
    """How many rooms one package needs for the stay night."""

    for item in getattr(product, "resources", []) or []:
        if str(getattr(item, "resource_type", "")) == "ROOM":
            return max(1, int(getattr(item, "quantity_per_package", 1) or 1))
    return 1


def _consecutive_rooms(product: Any, start: date | None, nights: int) -> bool:
    """Return True when the same room type is sellable for `nights` in a row.

    Room inventory rows are stored per night, so a multi-night package is only
    honest when every following night is still on sale for the same room type.
    """

    room = getattr(product, "room_inventory", None)
    if room is None or start is None:
        return False
    hotel = getattr(product, "hotel", None)
    inventory = list(getattr(hotel, "rooms", []) or []) if hotel is not None else []
    if not inventory:
        # No loaded inventory graph: trust the anchor night that produced the product.
        return nights == 1
    needed = _room_package_quantity(product)
    room_type = str(getattr(room, "room_type", "") or "")
    for offset in range(nights):
        day = start + timedelta(days=offset)
        match = next(
            (
                item
                for item in inventory
                if getattr(item, "available_date", None) == day
                and str(getattr(item, "room_type", "") or "") == room_type
                and str(getattr(item, "status", "") or "").upper() == "AVAILABLE"
                and int(getattr(item, "available_count", 0) or 0) >= needed
            ),
            None,
        )
        if match is None:
            return False
    return True


def build_stay_plan(product: Any, nights: int = DEFAULT_STAY_NIGHTS) -> dict[str, Any]:
    """Describe the hotel stay behind a package: nights, dates and price."""

    # The product owns its length of stay; the query parameter only mirrors it.
    bound_nights = max(DEFAULT_STAY_NIGHTS, min(int(getattr(product, "nights", None) or nights or DEFAULT_STAY_NIGHTS), MAX_STAY_NIGHTS))
    requested = bound_nights
    room = getattr(product, "room_inventory", None)
    check_in = getattr(room, "available_date", None) or getattr(product, "target_date", None)
    base_price = Decimal(str(getattr(product, "suggested_price", 0) or 0))
    night_price = Decimal(str(getattr(room, "normal_price", 0) or 0))
    room_name = next(
        (
            str(getattr(item, "resource_name", "") or "")
            for item in getattr(product, "resources", []) or []
            if str(getattr(item, "resource_type", "")) == "ROOM"
        ),
        "",
    )
    options: list[dict[str, Any]] = []
    for candidate in range(DEFAULT_STAY_NIGHTS, MAX_STAY_NIGHTS + 1):
        options.append(
            {
                "nights": candidate,
                "days": candidate + 1,
                "label": f"{candidate + 1}天{candidate}晚",
                "check_in": check_in.isoformat() if check_in else None,
                "check_out": (check_in + timedelta(days=candidate)).isoformat() if check_in else None,
                "price": str((base_price + night_price * (candidate - 1)).quantize(Decimal("0.01"))),
                "available": _consecutive_rooms(product, check_in, candidate),
            }
        )
    chosen = next((item for item in options if item["nights"] == requested and item["available"]), None)
    if chosen is None:
        chosen = next((item for item in reversed(options) if item["available"]), options[0])
    hotel = getattr(product, "hotel", None)
    chosen = dict(chosen)
    chosen.update(
        {
            "room_type": str(getattr(room, "room_type", "") or ""),
            "room_name": room_name or "舒适客房",
            "hotel_name": str(getattr(hotel, "name", "") or ""),
            "hotel_city": str(getattr(hotel, "city", "") or ""),
            "hotel_address": str(getattr(hotel, "address", "") or ""),
            "requested_nights": requested,
            "adjusted": int(chosen["nights"]) != requested,
            "max_nights": MAX_STAY_NIGHTS,
            "check_in_time": _CHECK_IN_TIME,
            "check_out_time": _CHECK_OUT_TIME,
            "options": options,
        }
    )
    return chosen


def _clock_minutes(value: object) -> int | None:
    match = re.match(r"^(\d{1,2}):(\d{2})", str(value or ""))
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


_SLOT_LABELS = {"MORNING": "上午", "AFTERNOON": "下午", "NIGHT": "晚上", "ALL_DAY": "全天", "ANY": "灵活"}


def _duration_minutes(item: dict[str, Any]) -> int | None:
    start = _clock_minutes(item.get("start_time"))
    end = _clock_minutes(item.get("end_time"))
    if start is None or end is None:
        return None
    span = end - start
    return span + 24 * 60 if span <= 0 else span


def _duration_text(duration: int | None) -> str:
    if not duration:
        return "时长按场次安排"
    if duration < 60:
        return f"约 {duration} 分钟"
    hours, minutes = divmod(duration, 60)
    return f"约 {hours} 小时" if minutes == 0 else f"约 {hours} 小时 {minutes} 分钟"


# 这些是「房型特色 / 房间服务」，不是行程体验：不应计入体验数量，也不该跟景点抢时间段。
ROOM_FEATURE_WORDS = ("影音", "会员", "电影", "投影", "桌游", "迷你吧")


def is_room_feature(name: object) -> bool:
    text = str(name or "")
    return any(word in text for word in ROOM_FEATURE_WORDS)


def is_checkout_service(item: dict[str, Any]) -> bool:
    """Checkout services belong to the departure day, never the arrival itinerary."""
    if str(item.get("resource_type") or "") != "HOTEL_SERVICE":
        return False
    name = str(item.get("resource_name") or "").lower()
    return any(word in name for word in ("退房", "checkout"))


def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_start = _clock_minutes(left.get("start_time"))
    left_end = _clock_minutes(left.get("end_time"))
    right_start = _clock_minutes(right.get("start_time"))
    right_end = _clock_minutes(right.get("end_time"))
    if None in (left_start, left_end, right_start, right_end):
        return False
    return left_start < right_end and right_start < left_end


def _slot_of(item: dict[str, Any], duration: int | None) -> str:
    """Half-day slot for one experience.

    Long single-attraction visits (theme parks and similar) take a whole day,
    otherwise the start time decides whether it belongs to the morning,
    afternoon or evening block.
    """

    if duration is not None and duration >= 240:
        return "ALL_DAY"
    minutes = _clock_minutes(item.get("start_time"))
    if minutes is None:
        return "ANY"
    if minutes < 12 * 60:
        return "MORNING"
    if minutes < 18 * 60:
        return "AFTERNOON"
    return "NIGHT"


def _experience_entry(item: dict[str, Any], fallback_description: str) -> dict[str, Any]:
    duration = _duration_minutes(item)
    slot = _slot_of(item, duration)
    start = str(item.get("start_time") or "")[:5]
    end = str(item.get("end_time") or "")[:5]
    return {
        "slot": slot,
        "slot_label": _SLOT_LABELS[slot],
        "time": f"{start}–{end}" if start and end else (start or ""),
        # 原始时间也带上（存成字符串，避免 time 对象无法 JSON 序列化），
        # 用于判断同一时间段是否冲突。
        "start_time": str(item.get("start_time") or "")[:8],
        "end_time": str(item.get("end_time") or "")[:8],
        "title": str(item.get("resource_name") or "行程安排"),
        "description": str(item.get("description") or fallback_description),
        "duration_minutes": duration,
        "duration_text": _duration_text(duration),
        "notes": str(item.get("booking_notice") or ""),
        "address": str(item.get("address") or ""),
        "kind": str(item.get("resource_type") or ""),
        "included": str(item.get("resource_type") or "") != "PUBLIC_REFERENCE",
    }


def _stay_entry(title: str, description: str, *, time_text: str, kind: str = "ROOM", slot: str = "ANY", address: str = "", included: bool | None = None) -> dict[str, Any]:
    return {
        "slot": slot,
        "slot_label": _SLOT_LABELS[slot],
        "time": time_text,
        "title": title,
        "description": description,
        "duration_minutes": None,
        "duration_text": "",
        "notes": "",
        "address": address,
        "kind": kind,
        "included": included if included is not None else kind not in {"PUBLIC_REFERENCE", "FREE", "BAGGAGE"},
    }


def _district(value: object) -> str:
    text = str(value or "")
    match = re.search(r"([\u4e00-\u9fff]{2,5}(?:区|县))", text)
    return match.group(1) if match else ""


def _address_is_specific(value: object) -> bool:
    text = str(value or "")
    if len(text) < 6:
        return False
    # A named, signed entrance is a usable destination even when the venue
    # does not publish a street number (museum gates, wharfs and theatres).
    named_entrance = re.search(r"(?:正门|南门|北门|东门|西门|游客中心|售票处|码头|剧院|博物馆|展馆|入口)", text)
    numbered_address = re.search(r"\d+\s*(?:号|弄|幢|栋|座|室)|(?:路|街|巷)\s*\d+", text)
    return bool(named_entrance or numbered_address)


def route_proximity(from_address: object, to_address: object) -> dict[str, Any]:
    """Compare address granularity and area without inventing map distances."""

    source = str(from_address or "").strip()
    target = str(to_address or "").strip()
    if not _address_is_specific(source) or not _address_is_specific(target):
        return {
            "label": "地址待补全",
            "buffer_minutes": None,
            "status": "unknown",
            "reason": "地址精度不足，路线按同城交通缓冲安排；补充场馆入口或门牌地址后可提高估算精度。",
        }
    source_district, target_district = _district(source), _district(target)
    shared = _areas(source) & _areas(target)
    if source_district and source_district == target_district:
        return {
            "label": f"同处{source_district} · 约25分钟转场",
            "buffer_minutes": 25,
            "status": "same_district",
            "reason": f"两处地址同在{source_district}，按同区路线顺序衔接，预留约20–30分钟交通时间。",
        }
    if shared:
        area = "、".join(sorted(shared))
        return {
            "label": f"同在{area}一带 · 约20分钟转场",
            "buffer_minutes": 20,
            "status": "same_area",
            "reason": f"两处地址都在{area}一带，可连续安排，预留约15–25分钟交通时间。",
        }
    if source_district and target_district:
        return {
            "label": f"{source_district} → {target_district} · 约40分钟转场",
            "buffer_minutes": 40,
            "status": "cross_district",
            "reason": f"路线从{source_district}跨到{target_district}，预留约30–45分钟交通时间，建议避免与紧邻场次硬接。",
        }
    return {
        "label": "地址可读，片区待核",
        "buffer_minutes": 35,
        "status": "area_unknown",
        "reason": "地址已录入，按约30–40分钟交通缓冲安排；当前地点数据不足以换算可靠公里数。",
    }


def _public_route_places(crowd_code: str, weather: str, hotel_address: str, resource_addresses: list[str], route_preference: str) -> list[dict[str, Any]]:
    """Rank public places as optional route ideas; they never become package resources."""

    preference = str(route_preference or "")
    indoor_first = "室内" in preference
    outdoor_first = "户外" in preference
    compact_route = any(word in preference for word in ("特种兵", "紧凑"))
    reference_addresses = [hotel_address, *resource_addresses]

    def score(place: dict[str, Any]) -> tuple[int, str]:
        value = 0
        crowds = str(place.get("suitable_crowds") or "").upper()
        if crowd_code and (crowd_code in crowds or "ALL" in crowds):
            value += 4
        place_weather = {item.strip().upper() for item in str(place.get("weather_adaptations") or "").split(",")}
        if weather and weather in place_weather:
            value += 2
        indoor = str(place.get("indoor_outdoor") or "").upper() == "INDOOR"
        if indoor_first:
            value += 5 if indoor else -2
        elif outdoor_first:
            value += 4 if not indoor else 0
        elif weather == "RAIN":
            value += 3 if indoor else -1
        address = str(place.get("address") or "")
        for reference in reference_addresses:
            district = _district(address)
            if district and district == _district(reference):
                value += 4
            value += 2 * len(_areas(address) & _areas(reference))
        if _address_is_specific(address):
            value += 1
        if compact_route and any(word in f"{place.get('category', '')} {place.get('name', '')}".upper() for word in ("SPORT", "THEME_PARK", "运动", "乐园", "徒步", "动物")):
            value += 3
        return value, str(place.get("name") or "")

    places = []
    for raw in CURATED_HANGZHOU_KNOWLEDGE:
        item = dict(raw)
        item.update({"resource_type": "PUBLIC_REFERENCE", "included": False})
        places.append(item)
    return sorted(places, key=score, reverse=True)


def _slot_summary(entries: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for slot in ("MORNING", "AFTERNOON", "NIGHT", "ALL_DAY"):
        names = [str(item["title"]) for item in entries if item.get("slot") == slot]
        if names:
            parts.append(f"{_SLOT_LABELS[slot]}：{'、'.join(dict.fromkeys(names))}")
    return " · ".join(parts)


def _route_intensity(name: object, category: object = "", duration: int | None = None) -> str:
    text = f"{name or ''} {category or ''}".upper()
    if duration is not None and duration >= 180 or any(word in text for word in ("攀岩", "卡丁车", "骑行", "徒步", "登山", "漂流", "动物互动", "运动", "SPORT", "THEME_PARK", "乐园")):
        return "高"
    if any(word in text for word in ("博物馆", "美术馆", "茶", "手作", "咖啡", "演出", "剧场", "漫步", "MUSEUM", "CULTURE", "FOOD", "CITY_WALK")):
        return "轻"
    return "中"


def build_day_plan(
    resources: list[dict[str, Any]],
    stay: dict[str, Any],
    *,
    crowd_code: str = "",
    weather: str = "",
    route_preference: str = "",
) -> list[dict[str, Any]]:
    """Build an address-aware, day-by-day route around the booked experience.

    Public places are explicitly suggestions, never package inventory or
    included benefits. Their opening and booking rules must be checked before
    travel because the curated public facts can change.
    """

    nights = max(DEFAULT_STAY_NIGHTS, int(stay.get("nights") or DEFAULT_STAY_NIGHTS))
    check_in = stay.get("check_in")
    try:
        start_date = date.fromisoformat(str(check_in)) if check_in else None
    except ValueError:
        start_date = None
    room_name = str(stay.get("room_name") or "酒店房间")
    hotel_address = str(stay.get("hotel_address") or "")
    luggage_included = any(
        str(item.get("resource_type") or "") == "HOTEL_SERVICE"
        and ("行李寄存" in str(item.get("resource_name") or "") or "行李寄存" in str(item.get("service_type") or ""))
        for item in resources
    )
    room_features = [
        item for item in resources
        if str(item.get("resource_type") or "") != "ROOM" and is_room_feature(item.get("resource_name"))
    ]
    experiences = [
        item for item in resources
        if str(item.get("resource_type") or "") != "ROOM"
        and not is_room_feature(item.get("resource_name"))
        and not is_checkout_service(item)
        and not (
            str(item.get("resource_type") or "") == "HOTEL_SERVICE"
            and any(word in str(item.get("resource_name") or "") for word in ("早餐", "行李寄存", "延迟退房", "欢迎饮品", "停车"))
        )
    ]
    entries = [_experience_entry(item, "现场由工作人员引导，建议提前 10 分钟抵达。") for item in experiences]
    entries.sort(key=lambda item: _clock_minutes(item.get("time", "").split("–")[0]) or 0)
    all_day = [item for item in entries if item["slot"] == "ALL_DAY"]
    compact_route = any(word in str(route_preference or "") for word in ("特种兵", "紧凑"))
    public_places = _public_route_places(
        crowd_code,
        str(weather or "").upper(),
        hotel_address,
        [str(item.get("address") or "") for item in experiences],
        route_preference,
    )

    def public_entry(place: dict[str, Any], time_text: str, slot: str, role: str) -> dict[str, Any]:
        duration = int(place.get("suggested_duration_minutes") or 90)
        open_note = str(place.get("opening_hours") or "开放安排请出发前核验。")
        booking_note = str(place.get("reservation_notice") or "预约规则请出发前核验。")
        status = str(place.get("verification_status") or "VERIFY_REQUIRED")
        verification = "公共路线建议，不包含门票、预约或交通费用。"
        return {
            "slot": slot,
            "slot_label": _SLOT_LABELS[slot],
            "time": time_text,
            "title": str(place.get("name") or "公共景点"),
            "description": str(place.get("description") or "") + " " + verification,
            "duration_minutes": duration,
            "duration_text": _duration_text(duration),
            "notes": " ".join(item for item in (open_note, booking_note) if item and not any(generic in item for generic in ("以当天官方公告为准", "请出发前核验", "请出发前核对"))),
            "address": str(place.get("address") or ""),
            "kind": "PUBLIC_REFERENCE",
            "included": False,
            "route_only": True,
            "area": str(place.get("area") or ""),
            "source_name": str(place.get("source_name") or ""),
            "source_url": str(place.get("source_url") or ""),
            "verification_status": status,
            "opening_hours": open_note,
            "reservation_notice": booking_note,
            "route_role": role,
        }

    def timed_minutes(entry: dict[str, Any], index: int = 0) -> int:
        return _clock_minutes(str(entry.get("time") or "").split("–")[0]) or index

    early_experience = any(
        (minute := _clock_minutes(item.get("start_time"))) is not None and minute < 15 * 60
        for item in entries
    )
    first_items: list[dict[str, Any]] = []
    if early_experience:
        first_items.append(
            _stay_entry(
                "先到酒店寄存行李",
                "行李寄存在酒店前台，完成后再前往当天第一项体验。",
                time_text="出发前",
                kind="BAGGAGE",
                slot="MORNING",
                address=hotel_address,
                included=luggage_included,
            )
        )
    morning_core = [item for item in entries if item["slot"] == "MORNING"]
    timed_core = [item for item in entries if item["slot"] != "ALL_DAY"]
    used_public_places: set[str] = set()

    def next_public(preferred_intensity: str | None = None) -> dict[str, Any] | None:
        available = [place for place in public_places if str(place.get("name") or "") not in used_public_places]
        if preferred_intensity:
            available.sort(key=lambda place: (_route_intensity(place.get("name"), place.get("category"), int(place.get("suggested_duration_minutes") or 0)) != preferred_intensity, public_places.index(place)))
        if not available:
            return None
        place = available[0]
        used_public_places.add(str(place.get("name") or ""))
        return place

    morning_activity = next((item for item in entries if item["slot"] == "MORNING"), None)
    morning_intensity = _route_intensity(morning_activity.get("title"), morning_activity.get("kind"), morning_activity.get("duration_minutes")) if morning_activity else "轻"
    preferred_afternoon = "高" if compact_route else ("轻" if morning_intensity == "高" else None)
    if not all_day and not morning_core:
        morning_place = next_public("轻" if weather == "RAIN" else None)
        if morning_place:
            first_items.append(public_entry(morning_place, "09:30–11:30", "MORNING", "入住日前半日路线"))
    if not any(_overlaps({"start_time": "12:00", "end_time": "13:00"}, item) for item in timed_core):
        first_items.append(_stay_entry("午餐与转场", "安排午餐，并预留前往下一站的交通时间；餐费不属于套餐。", time_text="12:00–13:00", kind="FREE", slot="AFTERNOON"))
    first_items.extend(entries)
    afternoon_core = next((item for item in entries if item["slot"] == "AFTERNOON"), None)
    if not all_day and not afternoon_core:
        afternoon_place = next_public(preferred_afternoon)
        if afternoon_place:
            afternoon = public_entry(afternoon_place, "13:30–15:00", "AFTERNOON", "午餐后城市体验")
            if morning_activity:
                if compact_route:
                    afternoon["description"] += f" 上午的{morning_activity['title']}后继续安排本段，整日节奏偏紧凑，适合主打高强度城市游。"
                elif morning_intensity == "高":
                    afternoon["description"] += f" 上午{morning_activity['title']}活动量较大，下午转为相对轻松的安排，给体力留出恢复时间。"
                else:
                    afternoon["description"] += f" 与上午{morning_activity['title']}形成有动有静的体验节奏。"
            first_items.append(afternoon)
        else:
            first_items.append({
                **_stay_entry("下午酒店周边漫游", "午餐后在酒店附近选择步行可达的街区或公共空间，安排轻松活动并预留入住时间。", time_text="13:30–15:00", kind="FREE", slot="AFTERNOON", address=hotel_address),
                "route_only": True,
            })
    elif morning_activity and afternoon_core:
        afternoon_intensity = _route_intensity(afternoon_core.get("title"), afternoon_core.get("kind"), afternoon_core.get("duration_minutes"))
        if compact_route and morning_intensity == "高" and afternoon_intensity == "高":
            afternoon_core["description"] += f" 上午{morning_activity['title']}后继续安排高强度项目，全天定位为紧凑型特种兵路线，建议按场次预留补水和用餐时间。"
        elif morning_intensity == "高" and afternoon_intensity == "轻":
            afternoon_core["description"] += f" 上午{morning_activity['title']}活动量较大，下午安排{afternoon_core['title']}放慢节奏，给体力留出恢复时间。"
        elif morning_intensity == "高" and afternoon_intensity == "高":
            afternoon_core["description"] += f" 上午{morning_activity['title']}后接着安排{afternoon_core['title']}，当天活动较密集，适合主打紧凑型城市游。"
    latest_overlap_end = max(
        (
            _clock_minutes(item.get("end_time"))
            for item in timed_core
            if _clock_minutes(item.get("start_time")) is not None
            and _clock_minutes(item.get("start_time")) < 15 * 60
            and (_clock_minutes(item.get("end_time")) or 0) > 15 * 60
        ),
        default=0,
    )
    checkin_minute = max(15 * 60, latest_overlap_end)
    checkin_time = f"{checkin_minute // 60:02d}:{checkin_minute % 60:02d} 后"
    first_items.append(
        _stay_entry(
            "办理入住 · 住一晚",
            f"回酒店办理入住{room_name}，行李已寄存的可在此时取回。",
            time_text=checkin_time,
            address=hotel_address,
        )
    )
    night_core = next((item for item in entries if item["slot"] == "NIGHT"), None)
    if not night_core:
        night_place = next_public("轻")
        if night_place:
            night = public_entry(night_place, "19:00–20:30", "NIGHT", "晚间可选轻松体验")
            night["title"] = f"晚间可选：{night['title']}"
            night["description"] += " 适合作为当天的轻松收尾，也可以直接回酒店休息。"
            first_items.append(night)
    feature_item = next((item for item in room_features if any(word in str(item.get("resource_name")) for word in ("影音", "会员", "电影", "投影"))), None)
    if feature_item is not None:
        first_items.append(_stay_entry(f"回房使用{feature_item.get('resource_name')}", "这是房型特色，按确认权益使用，不占白天活动时间。", time_text="21:30", kind="ROOM_FEATURE", slot="NIGHT", address=hotel_address))
    first_items.sort(key=timed_minutes)
    for index, item in enumerate(first_items):
        if item.get("address"):
            continue
        neighbours = sorted(
            (candidate for candidate in first_items if candidate.get("address")),
            key=lambda candidate: abs(timed_minutes(candidate, index) - timed_minutes(item, index)),
        )
        item["address"] = str((neighbours[0] if neighbours else {}).get("address") or hotel_address)

    days: list[dict[str, Any]] = [
        {
            "day_index": 1,
            "label": "第 1 天",
            "date": start_date.isoformat() if start_date else None,
            "title": "先寄存行李 · 城市体验 · 入住",
            "summary": ("先到酒店寄存行李，再前往体验点；公共景点为路线建议。" if early_experience else "按行程顺序开始城市体验，公共景点为路线建议。") + _slot_summary(first_items),
            "slot_summary": _slot_summary(first_items),
            "items": first_items,
        }
    ]

    for index in range(2, nights + 1):
        place_offset = len(used_public_places) + (index - 2) * 2
        middle_items = [
            _stay_entry("早餐与出发准备", "整理随身物品后从酒店出发；套餐包含的餐饮列在费用包含中。", time_text="08:00–09:00", kind="FREE", slot="MORNING", address=hotel_address)
        ]
        if place_offset < len(public_places):
            middle_items.append(public_entry(public_places[place_offset], "09:30–11:30", "MORNING", "同区公共路线参考"))
            used_public_places.add(str(public_places[place_offset].get("name") or ""))
        if place_offset + 1 < len(public_places):
            middle_items.append(public_entry(public_places[place_offset + 1], "14:00–16:00", "AFTERNOON", "下午公共路线参考"))
            used_public_places.add(str(public_places[place_offset + 1].get("name") or ""))
        middle_items.append(_stay_entry("返回酒店 · 继续住一晚", f"本产品包含的住宿为{room_name}；当晚按酒店规则使用房间。", time_text="21:00", slot="NIGHT", address=hotel_address))
        days.append({
            "day_index": index,
            "label": f"第 {index} 天",
            "date": (start_date + timedelta(days=index - 1)).isoformat() if start_date else None,
            "title": "继续游览 · 返回酒店",
            "summary": f"白天继续安排公共景点路线参考，晚间返回酒店。{_slot_summary(middle_items)}",
            "slot_summary": _slot_summary(middle_items),
            "items": middle_items,
        })

    last_index = nights + 1
    place_offset = len(used_public_places)
    last_items: list[dict[str, Any]] = [
        _stay_entry("早餐与整理行李", "早餐后整理行李，按计划办理退房。套餐包含的餐饮列在费用包含中。", time_text="08:00–09:00", kind="FREE", slot="MORNING", address=hotel_address),
    ]
    if place_offset < len(public_places):
        last_items.append(public_entry(public_places[place_offset], "09:00–10:30", "MORNING", "退房前上午路线参考"))
        used_public_places.add(str(public_places[place_offset].get("name") or ""))
    last_items.append(
        _stay_entry(
            "中午退房 · 行李寄存前台",
            "办理退房后将行李寄存在酒店前台，再安排下午路线；产品包含行李寄存服务。",
            time_text=_CHECK_OUT_TIME,
            kind="BAGGAGE",
            address=hotel_address,
            included=luggage_included,
        )
    )
    last_items.append(_stay_entry("午餐与转场", "用餐并预留前往下午地点的交通时间；餐费不属于套餐权益。", time_text="12:00–13:00", kind="FREE", slot="AFTERNOON"))
    if place_offset + 1 < len(public_places):
        last_items.append(public_entry(public_places[place_offset + 1], "13:30–15:30", "AFTERNOON", "退房后下午路线参考"))
        used_public_places.add(str(public_places[place_offset + 1].get("name") or ""))
    last_items.append(_stay_entry("返回酒店取行李", "下午行程结束后回酒店前台取回行李，再按返程安排出发。", time_text="15:30", kind="BAGGAGE", address=hotel_address, included=luggage_included))
    for index, item in enumerate(last_items):
        if item.get("address"):
            continue
        neighbours = sorted(
            (candidate for candidate in last_items if candidate.get("address")),
            key=lambda candidate: abs(timed_minutes(candidate, index) - timed_minutes(item, index)),
        )
        item["address"] = str((neighbours[0] if neighbours else {}).get("address") or hotel_address)
    days.append({
        "day_index": last_index,
        "label": f"第 {last_index} 天",
        "date": (start_date + timedelta(days=nights)).isoformat() if start_date else None,
        "title": "继续体验 · 退房返程",
        "summary": f"上午继续游览，中午退房并把行李寄存在前台，下午结束后回酒店取行李返程。{_slot_summary(last_items)}",
        "slot_summary": _slot_summary(last_items),
        "items": last_items,
    })
    return days


_AREA_WORDS = (
    "西湖", "湖滨", "运河", "拱宸桥", "小河直街", "良渚", "西溪", "湘湖", "龙井",
    "灵隐", "钱江新城", "钱塘江", "南山", "河坊街", "清河坊", "滨江", "城西",
    "城北", "武林", "九溪", "白塔", "天目里", "西湖区", "上城区", "拱墅区",
    "余杭区", "滨江区", "萧山区", "富阳区", "临平区", "钱塘区",
)


def _areas(*values: object) -> set[str]:
    text = " ".join(str(value or "") for value in values)
    return {word for word in _AREA_WORDS if word in text}


def _leg(from_name: str, from_address: str, to_name: str, to_address: str, *, location_pending: bool = False) -> dict[str, Any]:
    """Conservative transfer buffer from address relation; never claim map mileage."""

    if location_pending:
        return {
            "from_stop": from_name,
            "to_stop": to_name,
            "mode": "就近选址后核对",
            "minutes": 0,
            "distance_label": "地点待定",
            "note": "停留点尚未选定具体地址，暂不估算路程与耗时；请结合相邻景点就近安排。",
        }
    relation = route_proximity(from_address, to_address)
    if relation["status"] in {"same_district", "same_area"}:
        mode = "步行或短途交通"
    elif relation["status"] == "cross_district":
        mode = "打车或公共交通"
    else:
        mode = "出发前导航核验"
    minutes = int(relation.get("buffer_minutes") or 30)
    return {
        "from_stop": from_name,
        "to_stop": to_name,
        "mode": mode,
        "minutes": minutes,
        "distance_label": relation["label"],
        "note": relation["reason"],
    }


def build_route_plan(day_plan: list[dict[str, Any]], stay: dict[str, Any]) -> list[dict[str, Any]]:
    """A day-by-day route: ordered stops plus how to travel between them.

    The platform stores addresses rather than coordinates (no map key is
    configured), so the map is a schematic route with real addresses and
    practical travel hints instead of a hot-linked third-party map image.
    """

    room_name = str(stay.get("room_name") or "酒店")
    routes: list[dict[str, Any]] = []
    for day in day_plan:
        stops: list[dict[str, Any]] = []
        day_items = list(day.get("items", []))
        for item_index, item in enumerate(day_items):
            name = str(item.get("title") or "")
            kind = str(item.get("kind") or "")
            address = str(item.get("address") or "")
            if kind == "ROOM" and ("入住" in name or "退房" in name):
                address = address or str(stay.get("hotel_address") or "")
            if not address and kind in {"HOTEL_SERVICE", "BAGGAGE", "ROOM", "ROOM_FEATURE"}:
                address = str(stay.get("hotel_address") or "")
            if not address:
                nearby = next(
                    (str(candidate.get("address")) for offset in range(1, len(day_items) + 1)
                     for candidate_index in (item_index - offset, item_index + offset)
                     if 0 <= candidate_index < len(day_items)
                     and (candidate := day_items[candidate_index]).get("address")),
                    "",
                )
                address = nearby or str(stay.get("hotel_address") or "")
            stops.append(
                {
                    "time": str(item.get("time") or ""),
                    "title": name,
                    "address": address,
                    "kind": kind,
                    "slot": item.get("slot_label") or "",
                    "included": bool(item.get("included", kind not in {"PUBLIC_REFERENCE", "FREE", "BAGGAGE"})),
                    "route_only": bool(item.get("route_only", False)),
                    "source_name": str(item.get("source_name") or ""),
                    "source_url": str(item.get("source_url") or ""),
                    "verification_status": str(item.get("verification_status") or ""),
                }
            )
        if not stops:
            continue
        legs = [
            _leg(
                stops[index]["title"],
                stops[index]["address"],
                stops[index + 1]["title"],
                stops[index + 1]["address"],
                location_pending=not bool(stops[index]["address"] and stops[index + 1]["address"]),
            )
            for index in range(len(stops) - 1)
        ]
        routes.append(
            {
                "day_index": int(day.get("day_index") or len(routes) + 1),
                "label": str(day.get("label") or f"第 {len(routes) + 1} 天"),
                "date": day.get("date"),
                "title": str(day.get("title") or ""),
                "stops": stops,
                "legs": legs,
                "summary": f"共 {len(stops)} 站，{room_name}为出发与返回点。",
            }
        )
    return routes


def _reviews_for(product: Any) -> list[dict[str, Any]]:
    """Traveller reviews stored with the product.

    The visitor page shows the stored rating and count instead of a fixed
    score, so an unreviewed product renders no score at all.
    """

    reviews: list[dict[str, Any]] = []
    for item in getattr(product, "reviews", []) or []:
        reviews.append(
            {
                "id": int(getattr(item, "id", 0) or 0),
                "author_name": str(getattr(item, "author_name", "") or "旅人"),
                "author_tag": str(getattr(item, "author_tag", "") or ""),
                "rating": float(getattr(item, "rating", 0) or 0),
                "content": str(getattr(item, "content", "") or ""),
                "highlights": [str(value) for value in (getattr(item, "highlights", None) or [])],
                "source": str(getattr(item, "source", "") or "平台订单点评"),
                "stayed_on": getattr(item, "stayed_on", None).isoformat() if getattr(item, "stayed_on", None) else None,
            }
        )
    reviews.sort(key=lambda entry: (entry["stayed_on"] or "", entry["id"]), reverse=True)
    return reviews[:8]


def visitor_product_to_dict(product: Any, nights: int = DEFAULT_STAY_NIGHTS) -> dict[str, Any]:
    """Serialize a product for the public site without operator-only language."""

    data = product_to_dict(product)
    theme = str(data.get("theme") or "杭州周末")
    crowd = {"FAMILY": "亲子家庭", "COUPLE": "两人同行", "FRIENDS": "朋友出行", "SOLO": "独自旅行", "LOCAL_WEEKEND": "本地周末客"}.get(str(data.get("target_crowd") or ""), "旅人")
    resources = data.get("resources") or []
    visitor_copy = dict((getattr(product, "experience_notes", None) or {}).get("visitor_copy") or {})
    data["visitor_copy"] = visitor_copy
    resource_names = visitor_copy.get("resource_names") or {}
    for resource in resources:
        key = f"{resource.get('resource_type')}:{resource.get('resource_id')}"
        override = resource_names.get(key)
        if isinstance(override, str) and override.strip():
            resource["resource_name"] = public_travel_copy(override, str(resource.get("resource_name") or ""))
    stay = build_stay_plan(product, nights)
    data["stay"] = stay
    experience_names = [
        str(item.get("resource_name") or "")
        for item in resources
        if item.get("resource_name")
        and item.get("resource_type") != "ROOM"
    ]
    locations = [str(item.get("address")) for item in resources if item.get("address")]
    room_name = next((str(item.get("resource_name")) for item in resources if item.get("resource_type") == "ROOM" and item.get("resource_name")), "舒适客房")
    experience_text = "、".join(experience_names[:3]) or "在地体验"
    location_text = "、".join(dict.fromkeys(locations)) or "杭州城内"
    title_fallback = f"{theme}｜{crowd}住宿+在地体验"
    story_fallback = f"{stay.get('label') or '2天1晚'}住进{room_name}，前往{location_text}体验{experience_text}；每天的住宿、时间和顺序都已整理好。"
    reason_fallback = f"适合{crowd}，包含{experience_text}，从{location_text}开始即可按安排体验。"

    data["marketing_title"] = public_travel_copy(data.get("marketing_title"), title_fallback)
    data["marketing_content"] = public_travel_copy(data.get("marketing_content"), story_fallback)
    data["recommendation_reason"] = public_travel_copy(data.get("recommendation_reason"), reason_fallback)
    data["risk_message"] = public_travel_copy(
        data.get("risk_message"),
        "请按页面列出的集合地址和场次时间出发；需要无障碍、餐饮或同行安排时，可在下单备注。",
    )

    for resource in resources:
        name = str(resource.get("resource_name") or "体验项目")
        address = str(resource.get("address") or ("酒店内" if resource.get("resource_type") in {"ROOM", "HOTEL_SERVICE"} else "杭州"))
        start = str(resource.get("start_time") or "")[:5]
        end = str(resource.get("end_time") or "")[:5]
        time_text = f"，{start}–{end}" if start and end else ""
        if resource.get("resource_type") == "ROOM":
            fallback = (
                f"{name}含{stay.get('nights')}晚住宿（{stay.get('check_in') or ''} 入住、{stay.get('check_out') or ''} 退房），"
                f"到店后办理入住；早到时先将行李寄存在酒店前台，再按行程参加体验。"
            )
        elif resource.get("resource_type") == "HOTEL_SERVICE":
            fallback = f"{name}在酒店内使用{time_text or '，按当天行程安排'}，到店后向前台报商品名称即可。"
        else:
            fallback = f"{name}位于{address}{time_text}，现场由工作人员引导，建议提前10分钟抵达。"
        resource["description"] = public_travel_copy(resource.get("description"), fallback)

    data["day_plan"] = build_day_plan(
        resources,
        stay,
        crowd_code=str(data.get("target_crowd") or ""),
        weather=str(data.get("weather") or "").upper(),
    )
    resource_descriptions = visitor_copy.get("resource_descriptions") or {}
    for resource in resources:
        key = f"{resource.get('resource_type')}:{resource.get('resource_id')}"
        override = resource_descriptions.get(key)
        if isinstance(override, str) and override.strip():
            resource["description"] = public_travel_copy(override, resource.get("description") or "")
    itinerary_override = visitor_copy.get("itinerary") or []
    override_by_day = {int(item.get("day_index") or 0): item for item in itinerary_override if isinstance(item, dict)}
    for day in data["day_plan"]:
        override = override_by_day.get(int(day.get("day_index") or 0))
        if not override:
            continue
        for field in ("title", "summary"):
            value = override.get(field)
            if isinstance(value, str) and value.strip():
                day[field] = public_travel_copy(value, str(day.get(field) or ""))
        item_overrides = override.get("items") or []
        for index, day_item in enumerate(day.get("items") or []):
            if index >= len(item_overrides) or not isinstance(item_overrides[index], dict):
                continue
            for field in ("title", "description"):
                value = item_overrides[index].get(field)
                if isinstance(value, str) and value.strip():
                    day_item[field] = public_travel_copy(value, str(day_item.get(field) or ""))
    data["route_plan"] = build_route_plan(data["day_plan"], stay)
    data["reviews"] = _reviews_for(product)
    ratings = [float(item["rating"]) for item in data["reviews"]]
    data["rating_average"] = round(sum(ratings) / len(ratings), 1) if ratings else None
    data["rating_count"] = len(ratings)

    assets: list[dict[str, Any]] = []
    for raw_asset in data.get("marketing_assets") or []:
        asset = dict(raw_asset)
        for key in ("title", "content", "visual_brief", "creative_angle", "call_to_action"):
            if key in asset:
                asset[key] = public_travel_copy(asset.get(key), "")
        poster_svg = str(asset.get("poster_svg") or "")
        if poster_svg and not poster_svg.lstrip().lower().startswith("<svg"):
            asset["poster_svg"] = ""
        elif _INTERNAL_LANGUAGE.search(poster_svg):
            asset["poster_svg"] = _INTERNAL_LANGUAGE.sub("杭州旅居", poster_svg)
        assets.append(asset)
    data["marketing_assets"] = assets
    return data
