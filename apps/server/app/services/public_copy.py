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
        return "时长以现场安排为准"
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
    }


def _stay_entry(title: str, description: str, *, time_text: str, kind: str = "ROOM", slot: str = "ANY") -> dict[str, Any]:
    return {
        "slot": slot,
        "slot_label": _SLOT_LABELS[slot],
        "time": time_text,
        "title": title,
        "description": description,
        "duration_minutes": None,
        "duration_text": "",
        "notes": "",
        "address": "",
        "kind": kind,
    }


def _slot_summary(entries: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for slot in ("MORNING", "AFTERNOON", "NIGHT", "ALL_DAY"):
        names = [str(item["title"]) for item in entries if item.get("slot") == slot]
        if names:
            parts.append(f"{_SLOT_LABELS[slot]}：{'、'.join(dict.fromkeys(names))}")
    return " · ".join(parts)


def build_day_plan(resources: list[dict[str, Any]], stay: dict[str, Any]) -> list[dict[str, Any]]:
    """Split a hotel-anchored package into day-by-day travel-commerce copy.

    Day 1 always contains the check-in, afternoons and evenings run on the
    first day, mornings belong to the final day, and the remaining nights add
    full "stay + optional experience" days in between.
    """

    nights = max(DEFAULT_STAY_NIGHTS, int(stay.get("nights") or DEFAULT_STAY_NIGHTS))
    check_in = stay.get("check_in")
    try:
        start_date = date.fromisoformat(str(check_in)) if check_in else None
    except ValueError:
        start_date = None
    room_name = str(stay.get("room_name") or "酒店房间")
    # 影音会员这类属于房型特色：不计入「体验」，放到晚上回房使用。
    room_features = [
        item
        for item in resources
        if str(item.get("resource_type") or "") != "ROOM"
        and is_room_feature(item.get("resource_name"))
    ]
    experiences = [
        item
        for item in resources
        if str(item.get("resource_type") or "") != "ROOM"
        and not is_room_feature(item.get("resource_name"))
        and not is_checkout_service(item)
    ]
    places = [str(item.get("address")) for item in experiences if item.get("address")]

    entries = [_experience_entry(item, "现场由工作人员引导，建议提前 10 分钟抵达。") for item in experiences]
    entries.sort(key=lambda item: _clock_minutes(item.get("time", "").split("–")[0]) or 0)
    # 同一个时间段只留 1–2 项正式体验，时间冲突或超出的挪到「可选加购」。
    optional: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for entry in entries:
        same_slot = [item for item in kept if item["slot"] == entry["slot"]]
        if len(same_slot) >= 2 or any(_overlaps(entry, item) for item in kept):
            optional.append(entry)
            continue
        kept.append(entry)
    entries = kept
    all_day = [item for item in entries if item["slot"] == "ALL_DAY"]
    afternoon = [item for item in entries if item["slot"] == "AFTERNOON"]
    night = [item for item in entries if item["slot"] == "NIGHT"]
    morning = [item for item in entries if item["slot"] in {"MORNING", "ANY"}]

    first_items: list[dict[str, Any]] = [
        _stay_entry(
            "抵达杭州 · 办理入住",
            f"{room_name}的房间已按购买确认保留，放好行李、稍作休息后再开始今天的安排。",
            time_text=_CHECK_IN_TIME,
        ),
        *([] if all_day else afternoon),
        *night,
    ]
    if all_day:
        first_items[1:1] = [
            _stay_entry(
                "为明天的全天行程留出体力",
                "今天以入住和酒店周边为主，明天安排全天体验。",
                time_text="16:00",
                kind="FREE",
                slot="AFTERNOON",
            )
        ]
    if not afternoon and not night and not all_day:
        first_items.append(
            _stay_entry(
                "晚间自由安排",
                "酒店周边散步、晚餐或夜游都可以；旅居助手可以按同行人和天气再推荐一条路线。",
                time_text="18:30",
                kind="FREE",
                slot="NIGHT",
            )
        )
    feature_item = next(
        (
            item
            for item in room_features
            if any(word in str(item.get("resource_name")) for word in ("影音", "会员", "电影", "投影"))
        ),
        None,
    )
    if feature_item is not None:
        first_items.append(
            _stay_entry(
                f"回房使用{feature_item.get('resource_name')}",
                "晚上回到房间就能用；这是房型自带的特色，不计入行程体验，也不占白天时间。",
                time_text="21:30",
                kind="ROOM_FEATURE",
                slot="NIGHT",
            )
        )
    if optional:
        first_items.append(
            _stay_entry(
                "可选加购体验",
                "当天还有名额、但没有排进正式行程的项目："
                + "、".join(str(item["title"]) for item in optional[:3])
                + "；想加进套餐可以说一声，我会重新核对时间与名额。",
                time_text="",
                kind="OPTIONAL",
                slot="ANY",
            )
        )

    days: list[dict[str, Any]] = [
        {
            "day_index": 1,
            "label": "第 1 天",
            "date": start_date.isoformat() if start_date else None,
            "title": "抵达与入住",
            "summary": f"抵达后先入住{room_name}、放下行李，再按确认时间前往当天安排的地点。{_slot_summary(first_items)}",
            "slot_summary": _slot_summary(first_items),
            "items": first_items,
        }
    ]

    free_slot_used = False
    for index in range(2, nights + 1):
        # A longer stay must be filled with real content, not "free time".
        used_titles = {
            str(item.get("title"))
            for day in days
            for item in day["items"]
        }
        pending = [item for item in entries if str(item["title"]) not in used_titles]
        filled = pending[:3]
        if filled:
            middle_items = [
                _stay_entry("酒店早餐", "吃完早餐再出门，行李可以留在房间。", time_text="08:00–09:30", kind="HOTEL_SERVICE", slot="MORNING"),
                *filled,
                _stay_entry("返回酒店休息", f"今晚继续入住{room_name}，行李不需要挪动。", time_text="21:00", slot="NIGHT"),
            ]
        else:
            place_hint = "、".join(dict.fromkeys(places[:2])) or "西湖、运河一带"
            # 「自由安排」整个行程最多出现一次，其余半天都给到具体去处。
            if not free_slot_used:
                free_slot_used = True
                afternoon_item = _stay_entry(
                    "下午自选体验",
                    f"想加一段旅拍、手作或博物馆讲解都可以；若不加购，推荐到 {place_hint} 慢慢逛。",
                    time_text="14:00",
                    kind="FREE",
                    slot="AFTERNOON",
                )
            else:
                afternoon_item = _stay_entry(
                    "下午茶歇与街区漫步",
                    f"回酒店休息，或到 {place_hint} 附近喝一杯；按参考路线里的开放时间前往即可。",
                    time_text="14:00",
                    kind="HOTEL_SERVICE",
                    slot="AFTERNOON",
                )
            middle_items = [
                _stay_entry("酒店早餐", "今天不用赶路，先把早餐吃好再安排行程。", time_text="08:00–09:30", kind="HOTEL_SERVICE", slot="MORNING"),
                _stay_entry(
                    "上午在地漫步",
                    f"从酒店出发前往{place_hint}，参考路线上标注了开放时间与怎么去，全程约 2 小时。",
                    time_text="10:00",
                    kind="PARTNER_RESOURCE",
                    slot="MORNING",
                ),
                afternoon_item,
                _stay_entry("返回酒店休息", f"今晚继续入住{room_name}，行李不需要挪动。", time_text="21:00", slot="NIGHT"),
            ]
        days.append(
            {
                "day_index": index,
                "label": f"第 {index} 天",
                "date": (start_date + timedelta(days=index - 1)).isoformat() if start_date else None,
                "title": "住店慢游",
                "summary": f"睡到自然醒，上午、下午各留一段体验，晚上继续住店。{_slot_summary(middle_items)}",
                "slot_summary": _slot_summary(middle_items),
                "items": middle_items,
            }
        )

    last_index = nights + 1
    full_day_note = "全天只安排这一项，中途可按园区节奏休息。" if all_day else ""
    last_items: list[dict[str, Any]] = [
        *([] if all_day else [_stay_entry("酒店早餐", "早餐后整理行李，贵重物品请随身携带。", time_text="08:00–09:30", kind="HOTEL_SERVICE", slot="MORNING")]),
        *([] if all_day else morning),
        *all_day,
        _stay_entry(
            "办理退房 · 返程",
            "12:00 前办理退房；如果全天行程还没结束，可先把行李寄存在前台，结束后再返程。"
            if all_day
            else "12:00 前办理退房，行李可寄存在前台，继续逛杭州市区后再返程。",
            time_text=_CHECK_OUT_TIME,
        ),
    ]
    if all_day:
        last_items[0]["description"] = f"{last_items[0]['description']}{full_day_note}".strip()
    days.append(
        {
            "day_index": last_index,
            "label": f"第 {last_index} 天",
            "date": (start_date + timedelta(days=nights)).isoformat() if start_date else None,
            "title": "全天体验与返程" if all_day else "体验与返程",
            "summary": (
                f"全天体验后返程，全程共 {stay.get('label') or '2天1晚'}。{_slot_summary(last_items)}"
                if all_day
                else f"上午完成体验后退房返程，全程共 {stay.get('label') or '2天1晚'}。{_slot_summary(last_items)}"
            ),
            "slot_summary": _slot_summary(last_items),
            "items": last_items,
        }
    )
    return days


_AREA_WORDS = (
    "西湖", "湖滨", "运河", "拱宸桥", "小河直街", "良渚", "西溪", "湘湖", "龙井",
    "灵隐", "钱江新城", "钱塘江", "南山", "河坊街", "清河坊", "滨江", "城西",
    "城北", "武林", "九溪", "白塔", "天目里",
)


def _areas(*values: object) -> set[str]:
    text = " ".join(str(value or "") for value in values)
    return {word for word in _AREA_WORDS if word in text}


def _leg(from_name: str, from_address: str, to_name: str, to_address: str) -> dict[str, Any]:
    """Travel hint between two stops, derived from the areas they sit in."""

    source = _areas(from_name, from_address)
    target = _areas(to_name, to_address)
    if source and target and source & target:
        return {
            "from_stop": from_name,
            "to_stop": to_name,
            "mode": "步行",
            "minutes": 12,
            "note": f"同在{'、'.join(sorted(source & target))}一带，步行约 10–15 分钟，沿途可以顺路逛。",
        }
    if source and target:
        return {
            "from_stop": from_name,
            "to_stop": to_name,
            "mode": "打车或地铁",
            "minutes": 28,
            "note": f"从{'、'.join(sorted(source))}到{'、'.join(sorted(target))}，打车约 20–30 分钟；地铁需换乘 1 次。",
        }
    return {
        "from_stop": from_name,
        "to_stop": to_name,
        "mode": "打车",
        "minutes": 20,
        "note": "按导航前往即可，建议预留 10 分钟机动时间。",
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
        for item in day.get("items", []):
            name = str(item.get("title") or "")
            kind = str(item.get("kind") or "")
            address = str(item.get("address") or "")
            if kind == "ROOM" and ("入住" in name or "退房" in name):
                address = address or "酒店"
            if not address and kind == "HOTEL_SERVICE":
                address = "酒店内"
            stops.append(
                {
                    "time": str(item.get("time") or ""),
                    "title": name,
                    "address": address or "杭州",
                    "kind": kind,
                    "slot": item.get("slot_label") or "",
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
        "到店时间或加购需求可以在购买时备注，我们会按备注安排。",
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
                f"到店后办理入住；建议先放好行李，再按购买确认开始体验。"
            )
        elif resource.get("resource_type") == "HOTEL_SERVICE":
            fallback = f"{name}在酒店内使用{time_text or '，时间以购买确认信息为准'}，到店后向前台报商品名称即可。"
        else:
            fallback = f"{name}位于{address}{time_text}，现场由工作人员引导，建议提前10分钟抵达。"
        resource["description"] = public_travel_copy(resource.get("description"), fallback)

    data["day_plan"] = build_day_plan(resources, stay)
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
