"""Enrich the demo catalogue with realistic, per-product content.

Three gaps are closed here:

* every product gets a morning + afternoon experience (and an evening one for
  night-themed products) instead of a single activity;
* products receive stored reviews so the visitor page shows a real rating and
  review text tied to the actual resources;
* a few confirmed orders are pre-set so the hotel dashboard shows completed
  business instead of an empty revenue panel.

The script is idempotent: it only adds what is missing.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "server"))

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    PartnerResource,
    ProductResource,
    ProductReview,
    RoomInventory,
    TravelProduct,
    VisitorIntent,
)
from app.services.knowledge_service import KnowledgeService  # noqa: E402
from app.services.public_copy import _clock_minutes, _duration_minutes, _slot_of  # noqa: E402


NIGHT_KEYWORDS = ("夜", "音乐", "演出", "剧场", "点茶", "旅拍")
# Which experience categories read naturally next to the product's main
# activity, so a couple's canal-night package pairs with a museum or a
# workshop rather than an unrelated climbing session.
COMPLEMENTS = {
    "NIGHTLIFE": {"CULTURE", "TEA", "FOOD", "PHOTO"},
    "CULTURE": {"TEA", "FOOD", "NATURE", "PHOTO"},
    "THEME_PARK": {"FOOD", "CULTURE", "PHOTO"},
    "KIDS": {"NATURE", "CULTURE", "THEME_PARK"},
    "SPORT": {"FOOD", "ENTERTAINMENT"},
    "PHOTO": {"CULTURE", "TEA", "FOOD"},
    "FOOD": {"CULTURE", "NIGHTLIFE", "PHOTO"},
    "NATURE": {"CULTURE", "TEA", "FOOD"},
    "TEA": {"CULTURE", "NATURE"},
    "ENTERTAINMENT": {"FOOD", "NIGHTLIFE", "CULTURE"},
}
REVIEW_AUTHORS = [
    ("林女士", "亲子出行"), ("周先生", "两人同行"), ("陈女士", "亲子出行"),
    ("吴先生", "朋友出行"), ("沈女士", "独自旅行"), ("钱先生", "本地周末"),
    ("许女士", "两人同行"), ("郑先生", "亲子出行"),
]


def _slot_for(resource: PartnerResource) -> str:
    payload = {"start_time": resource.start_time, "end_time": resource.end_time}
    return _slot_of(payload, _duration_minutes(payload))


def _duration_label(duration: int | None) -> str:
    if not duration:
        return "时长以现场安排为准"
    if duration < 60:
        return f"约 {duration} 分钟"
    hours, minutes = divmod(duration, 60)
    return f"约 {hours} 小时" if minutes == 0 else f"约 {hours} 小时 {minutes} 分钟"


def _shares_place(resource_name: str, knowledge_name: str) -> bool:
    """True when two place names share a meaningful two-character term."""

    left = "".join(ch for ch in resource_name if "\u4e00" <= ch <= "\u9fff")
    right = "".join(ch for ch in knowledge_name if "\u4e00" <= ch <= "\u9fff")
    if not left or not right:
        return False
    grams_left = {left[index:index + 2] for index in range(len(left) - 1)}
    grams_right = {right[index:index + 2] for index in range(len(right) - 1)}
    return bool(grams_left & grams_right)


def _crowd_ok(resource: PartnerResource, crowd: str) -> bool:
    tags = str(resource.suitable_crowds or "").upper()
    return not tags or crowd in tags or "ALL" in tags


def _weather_ok(resource: PartnerResource, weather: str) -> bool:
    tags = str(resource.weather_tags or "").upper()
    return not tags or weather.upper() in tags


def _candidates(db, product: TravelProduct, used_ids: set[int], party_size: int) -> list[PartnerResource]:
    rows = list(
        db.scalars(
            select(PartnerResource).where(
                PartnerResource.available_date == product.target_date,
                PartnerResource.status == "AVAILABLE",
                PartnerResource.package_enabled.is_(True),
                PartnerResource.remaining_capacity >= party_size,
            )
        ).all()
    )
    pool = [
        item
        for item in rows
        if item.id not in used_ids
        and _slot_for(item) != "ALL_DAY"
        and _crowd_ok(item, product.target_crowd)
        and (_weather_ok(item, product.weather) or item.indoor)
    ]
    return pool


def _pick(
    pool: list[PartnerResource],
    slot: str,
    used_ids: set[int],
    merchants: set[int],
    complements: set[str],
    own_categories: set[str],
) -> PartnerResource | None:
    ranked = [
        item
        for item in pool
        # A whole-day attraction cannot be an add-on: it would replace the
        # product's existing half-day plan instead of complementing it.
        if item.id not in used_ids and _slot_for(item) == slot
    ]
    if not ranked:
        return None
    ranked.sort(
        key=lambda item: (
            # Stay on the product's own theme first: a slow-coffee weekend gets
            # another food/city experience, not an unrelated museum.
            0 if str(item.category or "").upper() in own_categories else 1 if str(item.category or "").upper() in complements else 2,
            0 if item.merchant_id not in merchants else 1,
            -int(item.market_price or 0),
            item.id,
        )
    )
    return ranked[0]


def enrich_experiences(db) -> int:
    """Give every product a morning and an afternoon experience."""

    added = 0
    products = list(db.scalars(select(TravelProduct).order_by(TravelProduct.id)).all())
    for product in products:
        partner_rows = [row for row in product.resources if row.resource_type == "PARTNER_RESOURCE"]
        sources: dict[int, PartnerResource] = {}
        for row in partner_rows:
            resource = db.get(PartnerResource, row.resource_id)
            if resource:
                sources[row.resource_id] = resource
        used_ids = set(sources)
        merchants = {item.merchant_id for item in sources.values()}
        slots = {_slot_for(item) for item in sources.values()}
        wanted = ["MORNING", "AFTERNOON"]
        text = f"{product.product_name} {product.theme}"
        if any(word in text for word in NIGHT_KEYWORDS):
            wanted.append("NIGHT")
        complements: set[str] = set()
        own_categories: set[str] = set()
        for resource in sources.values():
            category = str(resource.category or "").upper()
            own_categories.add(category)
            complements.update(COMPLEMENTS.get(category, set()))
        if not complements:
            complements = {"CULTURE", "FOOD", "NATURE"}
        complements -= own_categories
        party_size = max(1, int(product.party_size or 2))
        for slot in wanted:
            if slot in slots:
                continue
            pool = _candidates(db, product, used_ids, party_size)
            choice = _pick(pool, slot, used_ids, merchants, complements, own_categories)
            if choice is None:
                continue
            db.add(
                ProductResource(
                    product_id=product.id,
                    resource_type="PARTNER_RESOURCE",
                    resource_id=choice.id,
                    resource_name=choice.resource_name,
                    quantity_per_package=1,
                    unit_cost=choice.settlement_price,
                    replaceable=False,
                    required=False,
                )
            )
            used_ids.add(choice.id)
            if choice.merchant_id:
                merchants.add(choice.merchant_id)
            slots.add(slot)
            added += 1
    db.flush()
    return added


def _review_text(product: TravelProduct, rows: list[tuple[ProductResource, PartnerResource]], index: int) -> str:
    """Write one distinct review per index from the product's own facts."""

    room = next((row.resource_name for row in product.resources if row.resource_type == "ROOM"), "酒店房间")
    first = rows[0][1] if rows else None
    second = rows[1][1] if len(rows) > 1 else None
    third = rows[2][1] if len(rows) > 2 else None

    def window(resource: PartnerResource | None) -> str:
        if resource and resource.start_time and resource.end_time:
            return f"{resource.start_time.strftime('%H:%M')}–{resource.end_time.strftime('%H:%M')}"
        return "按确认时间"

    address = (first.address if first and first.address else "体验点")
    family_line = (
        f"带娃出行最看重节奏，第二天上午{second.resource_name if second else '的体验'}（{window(second)}）不用早起赶路，中午退房前还来得及吃早餐。"
        if product.target_crowd == "FAMILY"
        else f"行程节奏刚好，第二天上午{second.resource_name if second else '的体验'}（{window(second)}）不赶时间，退房前还能慢慢吃个早餐。"
    )
    companion = {
        "FRIENDS": "和朋友的这趟",
        "COUPLE": "两个人的周末",
        "SOLO": "一个人的这趟",
        "LOCAL_WEEKEND": "周末这趟",
    }.get(product.target_crowd, "这趟出行")
    templates = [
        f"订的是{room}，15:00 办好入住直接去{first.resource_name if first else '体验点'}（{window(first)}），{address}导航很好找，结束回酒店不到十分钟。",
        family_line,
        f"对比了同价位的套餐，{product.theme}这一组把住宿和{first.resource_name if first else '体验'}都写清楚了，{window(first)}到场就行，不用自己再排行程。",
        f"{companion}很省心，{first.resource_name if first else '体验'}在{address}，结束后回{room}休息，第二天退房把行李寄存在前台又逛了半天。",
        f"{third.resource_name + '是意外惊喜，' if third else ''}工作人员提前一天确认了集合点，当天{window(first)}到现场，全程没有额外收费。",
    ]
    return templates[index % len(templates)]


def _rename_products(db) -> int:
    """Drop the fixed "· 杭州一晚" suffix: not every package is one night."""

    renamed = 0
    for product in db.scalars(select(TravelProduct)):
        name = str(product.product_name or "")
        cleaned = name
        for suffix in (" · 杭州一晚", "· 杭州一晚", " · 杭州两晚", " · 杭州三晚"):
            cleaned = cleaned.replace(suffix, "")
        # Variants picked up a "资源A、资源B｜房型" name while they were created;
        # read them back as "<theme>（房型）".
        if "｜" in cleaned:
            room = db.get(RoomInventory, product.room_inventory_id)
            base = str(product.theme or "").split("·")[0] or "杭州周末"
            cleaned = f"{base}（{room.room_type}）" if room else base
        if cleaned != name:
            product.product_name = cleaned.strip()
            renamed += 1
    db.flush()
    return renamed


def _marketing_assets(db, product: TravelProduct) -> list[dict[str, Any]]:
    """Build personalised assets: poster, social post, short-video script, card."""

    from app.services.poster_service import poster_asset

    rows: list[PartnerResource] = []
    for row in product.resources:
        if row.resource_type != "PARTNER_RESOURCE":
            continue
        resource = db.get(PartnerResource, row.resource_id)
        if resource:
            rows.append(resource)
    rows.sort(key=lambda item: _clock_minutes(item.start_time.strftime("%H:%M")) if item.start_time else 0)
    room = next((row.resource_name for row in product.resources if row.resource_type == "ROOM"), "酒店客房")
    # The poster should use the product's own current photo, so the hero image
    # is taken from the primary experience (falling back to the room).
    hero_image = ""
    for row in product.resources:
        if row.resource_type != "PARTNER_RESOURCE":
            continue
        source = db.get(PartnerResource, row.resource_id)
        if source is not None and getattr(source, "image_url", ""):
            hero_image = str(source.image_url)
            break
    if not hero_image:
        room_row = db.get(RoomInventory, product.room_inventory_id)
        hero_image = str(getattr(room_row, "image_url", "") or "")
    morning = [item for item in rows if _slot_for(item) == "MORNING"]
    afternoon = [item for item in rows if _slot_for(item) == "AFTERNOON"]
    night = [item for item in rows if _slot_for(item) == "NIGHT"]
    parts = []
    if morning:
        parts.append("上午 " + "、".join(item.resource_name for item in morning))
    if afternoon:
        parts.append("下午 " + "、".join(item.resource_name for item in afternoon))
    if night:
        parts.append("晚上 " + "、".join(item.resource_name for item in night))
    schedule = " · ".join(parts) or "住宿 + 在地体验"
    address = next((item.address for item in rows if item.address), "杭州")
    times = [
        f"{item.resource_name} {item.start_time.strftime('%H:%M')}–{item.end_time.strftime('%H:%M')}"
        for item in rows[:3]
        if item.start_time and item.end_time
    ]
    title = f"{product.theme}｜{room}+{rows[0].resource_name}" if rows else product.product_name
    content = (
        f"住{room}，{schedule}。"
        + ("时间：" + "；".join(times) + "。" if times else "")
        + f"价格为 {product.suggested_price} 元，含住宿、体验与现场服务。"
    )
    poster = poster_asset(
        title=title,
        content=content,
        partner_name="、".join(item.resource_name for item in rows[:2]) or "在地体验",
        room_name=room,
        address=address,
        price=str(product.suggested_price),
        target_crowd=product.target_crowd,
        theme=product.theme,
        weather=product.weather,
        target_date=product.target_date.isoformat(),
        stay_label=f"{product.nights if hasattr(product, 'nights') else 1} 晚 · 含住宿",
        experience_line=schedule,
        highlights=[
            f"{item.start_time.strftime('%H:%M') if item.start_time else ''} {item.resource_name}".strip()
            for item in rows[:3]
        ],
        route_stops=[
            *(f"{item.resource_name[:8]}" for item in rows[:3]),
        ],
        hero_image_url=hero_image or None,
        variant_index=product.id % 3,
    )
    crowd_text = {"FAMILY": "带娃出行", "COUPLE": "两个人", "FRIENDS": "朋友同行", "SOLO": "一个人", "LOCAL_WEEKEND": "本地周末"}.get(product.target_crowd, "周末出行")
    return [
        {
            "asset_type": "POSTER",
            "platform": "海报",
            "title": title,
            "content": content,
            "visual_brief": f"{product.theme}主视觉，突出{schedule}",
            "call_to_action": "查看可订日期",
            "poster_svg": poster["poster_svg"],
            "poster_style": poster["poster_style"],
            "creative_angle": poster["creative_angle"],
        },
        {
            "asset_type": "SOCIAL_POST",
            "platform": "小红书",
            "title": f"{crowd_text}的杭州周末：{product.theme}",
            "content": f"{content}\n地址：{address}\n推荐给：{crowd_text}\n#杭州周末 #{product.theme} #住宿加体验",
            "visual_brief": "出行记录风，实景照片配手写标注",
            "call_to_action": "想要同款行程可以留言",
            "creative_angle": "以真实行程顺序做种草笔记",
        },
        {
            "asset_type": "SHORT_VIDEO_SCRIPT",
            "platform": "短视频",
            "title": f"{product.theme} 15 秒脚本",
            "content": (
                f"0-3s 酒店大堂与{room}展示；"
                f"3-8s {'；'.join(times) or schedule}；"
                f"8-12s 体验现场画面与餐食；"
                f"12-15s 价格 {product.suggested_price} 元与预订方式。"
            ),
            "visual_brief": "横屏实拍，字幕标出时间与地点",
            "call_to_action": "评论区回复日期即可预订",
            "creative_angle": "按时间轴剪出行程节奏",
        },
        {
            "asset_type": "STORE_CARD",
            "platform": "门店展示",
            "title": f"{product.product_name}",
            "content": f"{schedule}｜住宿：{room}｜{product.nights if hasattr(product, 'nights') else 1} 晚｜{product.suggested_price} 元/套",
            "visual_brief": "柜台立牌，正面写行程与价格",
            "call_to_action": "前台可直接咨询",
            "creative_angle": "适合前台与客房内展示",
        },
    ]


def refresh_marketing_assets(db, *, force: bool = False) -> int:
    updated = 0
    for product in db.scalars(select(TravelProduct).order_by(TravelProduct.id)).all():
        assets = product.marketing_assets if isinstance(product.marketing_assets, list) else []
        if not force and assets and any(asset.get("poster_svg") for asset in assets if isinstance(asset, dict)):
            continue
        product.marketing_assets = _marketing_assets(db, product)
        updated += 1
    db.flush()
    return updated


def seed_reviews(db) -> int:
    created = 0
    products = list(db.scalars(select(TravelProduct).order_by(TravelProduct.id)).all())
    for product in products:
        existing = db.scalar(select(ProductReview).where(ProductReview.product_id == product.id).limit(1))
        if existing:
            continue
        rows: list[tuple[ProductResource, PartnerResource]] = []
        for row in product.resources:
            if row.resource_type != "PARTNER_RESOURCE":
                continue
            resource = db.get(PartnerResource, row.resource_id)
            if resource:
                rows.append((row, resource))
        rows.sort(key=lambda pair: _clock_minutes(pair[1].start_time.strftime("%H:%M")) or 0 if pair[1].start_time else 0)
        ratings = [Decimal("5.0"), Decimal("4.5"), Decimal("4.5"), Decimal("5.0"), Decimal("4.0")]
        for index in range(3):
            author, tag = REVIEW_AUTHORS[(product.id + index) % len(REVIEW_AUTHORS)]
            rating = ratings[(product.id + index) % len(ratings)]
            db.add(
                ProductReview(
                    product_id=product.id,
                    author_name=author,
                    author_tag=tag,
                    rating=rating,
                    content=_review_text(product, rows, index),
                    highlights=[resource.resource_name for _, resource in rows[:3]],
                    source="平台订单点评",
                    stayed_on=(product.target_date + timedelta(days=index)),
                )
            )
            created += 1
    db.flush()
    return created


def seed_orders(db) -> int:
    existing = db.scalar(select(VisitorIntent).limit(1))
    if existing:
        return 0
    products = list(
        db.scalars(
            select(TravelProduct)
            .where(TravelProduct.status.in_(("ON_SALE", "LOW_STOCK")))
            .order_by(TravelProduct.id)
        ).all()
    )
    if not products:
        return 0
    now = datetime.now(timezone.utc)
    people = [
        ("林女士", "138****2266", 2, 1, ["博物馆", "亲子"]),
        ("周先生", "139****5188", 2, 0, ["夜游", "旅拍"]),
        ("陈女士", "137****9041", 3, 1, ["手作", "美食"]),
        ("吴先生", "136****7712", 4, 0, ["运动", "朋友聚会"]),
        ("沈女士", "135****3390", 1, 0, ["咖啡", "看展"]),
        ("钱先生", "133****6621", 2, 1, ["乐园", "亲子"]),
    ]
    created = 0
    for offset, (name, phone, adults, children, interests) in enumerate(people):
        product = products[offset % len(products)]
        confirmed_at = now - timedelta(days=offset, hours=3)
        status = "CANCELLED" if offset == len(people) - 1 else "CONFIRMED"
        db.add(
            VisitorIntent(
                product_id=product.id,
                natural_language=f"{adults} 位成人{('、' + str(children) + ' 个孩子') if children else ''}，预算 {int(product.suggested_price)} 元，想体验{'、'.join(interests)}。",
                adult_count=adults,
                child_count=children,
                child_ages=[6] * children,
                budget=product.suggested_price,
                interests=interests,
                negative_interests=[],
                activity_level="MEDIUM",
                dietary_restrictions=[],
                allergy_information="",
                arrival_time=time(15, 0),
                preferred_experience_time=time(16, 0),
                other_requirements=f"{name}已电话确认场次，按购买信息出行。",
                recommendation_result=None,
                intent_status="FOLLOWING" if status == "CONFIRMED" else "CLOSED",
                reservation_status=status,
                reserved_until=confirmed_at + timedelta(hours=48),
                allocation_snapshot=None,
                released_at=None if status == "CONFIRMED" else confirmed_at,
                confirmed_at=confirmed_at,
                contact_name=name,
                contact_phone=phone,
            )
        )
        created += 1
    db.flush()
    return created


def refresh_copy(db) -> int:
    """Rewrite product marketing copy so it matches the real day structure."""

    knowledge = KnowledgeService(db)
    updated = 0
    products = list(db.scalars(select(TravelProduct).order_by(TravelProduct.id)).all())
    for product in products:
        rows = []
        for row in product.resources:
            if row.resource_type != "PARTNER_RESOURCE":
                continue
            resource = db.get(PartnerResource, row.resource_id)
            if resource:
                rows.append(resource)
        if not rows:
            continue
        rows.sort(key=lambda item: _clock_minutes(item.start_time.strftime("%H:%M")) if item.start_time else 0)
        room = next((row.resource_name for row in product.resources if row.resource_type == "ROOM"), "酒店客房")
        morning = [item for item in rows if _slot_for(item) == "MORNING"]
        afternoon = [item for item in rows if _slot_for(item) == "AFTERNOON"]
        night = [item for item in rows if _slot_for(item) == "NIGHT"]
        parts = [
            f"第 1 天 15:00 后入住{room}，"
            + ("下午安排" + "、".join(item.resource_name for item in afternoon) + "，" if afternoon else "")
            + ("晚上安排" + "、".join(item.resource_name for item in night) + "，" if night else "")
            + "其余时间可自由安排。",
            "第 2 天"
            + ("上午安排" + "、".join(item.resource_name for item in morning) + "，" if morning else "")
            + "12:00 前办理退房，行李可寄存在前台。",
        ]
        detail_lines = []
        for item in rows[:3]:
            duration = _duration_minutes({"start_time": item.start_time, "end_time": item.end_time})
            window = (
                f"{item.start_time.strftime('%H:%M')}–{item.end_time.strftime('%H:%M')}"
                if item.start_time and item.end_time
                else "时间以购买确认为准"
            )
            note = str(item.booking_notice or "").strip()
            detail_lines.append(
                f"{item.resource_name}（{window}，{_duration_label(duration)}）：{item.description}"
                + (f" 注意：{note}" if note else "")
            )
        # Only quote a knowledge record that is genuinely about the same place,
        # otherwise unrelated records leak their keywords into the product copy
        # and the visitor assistant starts matching on the wrong theme.
        source_line = ""
        for candidate in knowledge.search(rows[0].resource_name, limit=5):
            if _shares_place(rows[0].resource_name, str(candidate.get("name") or "")):
                source_line = f"公开资料参考：{candidate['description']}（来源：{candidate['source_name']}）"
                break
        product.marketing_title = f"{product.theme}｜{room}+{rows[0].resource_name}"
        product.marketing_content = " ".join(parts + detail_lines + ([source_line] if source_line else []))
        product.recommendation_reason = (
            f"住宿与{len(rows)} 项体验按半天节奏排好："
            + "、".join(item.resource_name for item in rows[:4])
            + f"；适合{product.party_size} 人同行。"
        )
        product.risk_message = (
            "户外体验遇雨会调整顺序或改期；儿童年龄、饮食与过敏信息请在购买时填写，"
            "涉水、攀爬等项目请以现场安全说明为准。"
        )
        updated += 1
    db.flush()
    return updated


def create_room_variants(db) -> int:
    """Sell several different packages on the same room type and night.

    One physical room type should support more than one experience组合; the
    packages then share that night's room pool, so selling out the room type
    sells out every package built on it.
    """

    from uuid import uuid4

    created = 0
    for product in list(db.scalars(select(TravelProduct).order_by(TravelProduct.id)).all()):
        if not str(product.product_code).startswith("SC-"):
            continue
        # Variants carry a "·" in the theme; only base packages spawn one.
        if "·" in str(product.theme or ""):
            continue
        existing_variants = int(db.scalar(
            select(func.count()).select_from(TravelProduct).where(
                TravelProduct.room_inventory_id == product.room_inventory_id,
                TravelProduct.theme.like(f"{product.theme}%"),
                TravelProduct.id != product.id,
            )
        ) or 0)
        if existing_variants >= 2:
            continue
        room = db.get(RoomInventory, product.room_inventory_id)
        if room is None:
            continue
        used_ids = {row.resource_id for row in product.resources if row.resource_type == "PARTNER_RESOURCE"}
        party_size = max(1, int(product.party_size or 2))
        pool = _candidates(db, product, used_ids, party_size)
        # A different category keeps the second package visibly different.
        own_categories = {
            str(db.get(PartnerResource, row.resource_id).category or "").upper()
            for row in product.resources
            if row.resource_type == "PARTNER_RESOURCE" and db.get(PartnerResource, row.resource_id)
        }
        picks: list[PartnerResource] = []
        # Later variants skip the resources already used by earlier ones so the
        # same room type offers visibly different packages.
        offset = existing_variants * 2
        for candidate in pool[offset:]:
            if str(candidate.category or "").upper() in own_categories:
                continue
            picks.append(candidate)
            if len(picks) == 2:
                break
        if len(picks) < 2:
            continue
        total_cost = Decimal(str(room.accounting_cost or 0))
        for item in picks:
            total_cost += Decimal(str(item.settlement_price or 0))
        price = (Decimal(str(product.suggested_price or 0)) + Decimal("60")).quantize(Decimal("0.01"))
        margin_price = (total_cost / Decimal("0.80")).quantize(Decimal("0.01"))
        price = max(price, margin_price)
        variant = TravelProduct(
            hotel_id=product.hotel_id,
            product_code=f"SC-{product.target_date.strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}",
            product_name=f"{'、'.join(item.resource_name for item in picks)}｜{room.room_type}",
            theme=f"{product.theme}·{'、'.join(item.resource_name[:4] for item in picks)}",
            target_crowd=product.target_crowd,
            party_size=party_size,
            nights=getattr(product, "nights", 1) or 1,
            weather=product.weather,
            target_date=product.target_date,
            room_inventory_id=product.room_inventory_id,
            listed_quantity=int(room.available_count or 0),
            sale_quantity=int(room.available_count or 0),
            unit_cost=total_cost,
            minimum_allowed_price=margin_price,
            suggested_price=price,
            gross_profit=(price - total_cost).quantize(Decimal("0.01")),
            gross_margin=((price - total_cost) / price).quantize(Decimal("0.000001")),
            minimum_gross_margin_requirement=Decimal("0.20"),
            visitor_budget_limit=price + Decimal("200"),
            price_anchor=price,
            bottleneck_resource=room.room_type,
            status="ON_SALE",
            marketing_title="",
            marketing_content="",
            marketing_assets=[],
            recommendation_reason="",
            risk_message="",
        )
        db.add(variant)
        db.flush()
        db.add(
            ProductResource(
                product_id=variant.id,
                resource_type="ROOM",
                resource_id=room.id,
                resource_name=room.room_type,
                quantity_per_package=1,
                unit_cost=Decimal(str(room.accounting_cost or 0)),
                replaceable=False,
                required=True,
            )
        )
        for item in picks:
            db.add(
                ProductResource(
                    product_id=variant.id,
                    resource_type="PARTNER_RESOURCE",
                    resource_id=item.id,
                    resource_name=item.resource_name,
                    quantity_per_package=1,
                    unit_cost=Decimal(str(item.settlement_price or 0)),
                    replaceable=False,
                    required=False,
                )
            )
        created += 1
    db.flush()
    return created


ROOM_DETAIL_BY_TYPE: dict[str, str] = {
    "大床房": "28㎡ · 1.8 米大床 · 落地窗 · 可住 2 人",
    "双床房": "30㎡ · 1.2 米双床 ×2 · 独立书桌 · 可住 2 人",
    "湖景大床房": "32㎡ · 1.8 米大床 · 湖景落地窗 · 可住 2 人",
    "城市景观房": "30㎡ · 1.8 米大床 · 城市天际线视野 · 可住 2 人",
    "亲子房": "35㎡ · 1.8 米大床 + 儿童床 · 儿童用品齐备 · 可住 3 人",
    "亲子联通房": "42㎡ · 两间连通 · 1.8 米大床 + 双床 · 可住 4 人",
    "家庭套房": "48㎡ · 一室一厅 · 可加儿童床 · 可住 4 人",
    "庭院主题房": "34㎡ · 1.8 米大床 · 独立小院 · 可住 2 人",
    "影音娱乐房": "33㎡ · 1.8 米大床 · 投影与桌游 · 可住 2–3 人",
    "江景大床房": "36㎡ · 1.8 米大床 · 钱塘江景落地窗 · 可住 2 人",
    "露台景观房": "38㎡ · 1.8 米大床 · 独立露台 · 可住 2 人",
    "行政套房": "52㎡ · 一室一厅 · 独立会客区 · 可住 2–3 人",
    "榻榻米大床房": "31㎡ · 榻榻米地台 · 适合亲子的低床设计 · 可住 3 人",
    "双卧家庭房": "55㎡ · 两间卧室 · 可住 4–5 人",
}

# Extra room types are derived from an existing row of the same date so the
# catalogue keeps a realistic price structure without another seed file.
EXTRA_ROOM_TYPES: tuple[tuple[str, str, int, str, str], ...] = (
    ("江景大床房", "湖景大床房", 120, "COUPLE,SOLO,LOCAL_WEEKEND", "江景,落地窗,纪念日"),
    ("露台景观房", "庭院主题房", 90, "COUPLE,FRIENDS,LOCAL_WEEKEND", "露台,夜景,朋友"),
    ("行政套房", "家庭套房", 260, "COUPLE,LOCAL_WEEKEND,FRIENDS", "会客区,宽敞,商务"),
    ("榻榻米大床房", "亲子房", 60, "FAMILY,COUPLE", "榻榻米,低床,亲子"),
    ("双卧家庭房", "家庭套房", 180, "FAMILY,FRIENDS", "双卧,多人,家庭"),
)


def add_extra_room_types(db) -> int:
    """Widen the room catalogue so one package can be booked in more rooms."""

    created = 0
    for hotel_id in {int(item.hotel_id) for item in db.scalars(select(RoomInventory))}:
        dates = {item.available_date for item in db.scalars(select(RoomInventory).where(RoomInventory.hotel_id == hotel_id))}
        for target_date in sorted(dates):
            for room_type, base_type, price_delta, crowds, tags in EXTRA_ROOM_TYPES:
                exists = db.scalar(
                    select(RoomInventory.id).where(
                        RoomInventory.hotel_id == hotel_id,
                        RoomInventory.room_type == room_type,
                        RoomInventory.available_date == target_date,
                    )
                )
                if exists:
                    continue
                base = db.scalar(
                    select(RoomInventory).where(
                        RoomInventory.hotel_id == hotel_id,
                        RoomInventory.room_type == base_type,
                        RoomInventory.available_date == target_date,
                    )
                )
                source = base or db.scalar(
                    select(RoomInventory).where(
                        RoomInventory.hotel_id == hotel_id,
                        RoomInventory.available_date == target_date,
                    )
                )
                if source is None:
                    continue
                db.add(
                    RoomInventory(
                        hotel_id=hotel_id,
                        room_type=room_type,
                        available_date=target_date,
                        available_count=max(1, min(4, int(source.available_count or 2))),
                        normal_price=Decimal(str(source.normal_price or 0)) + Decimal(price_delta),
                        minimum_price=Decimal(str(source.minimum_price or 0)) + Decimal(price_delta),
                        accounting_cost=Decimal(str(source.accounting_cost or 0)) + Decimal(price_delta // 2),
                        max_guests=max(2, int(source.max_guests or 2)),
                        features=ROOM_DETAIL_BY_TYPE.get(room_type, source.features or room_type),
                        suitable_crowds=crowds,
                        tags=tags,
                        status="AVAILABLE",
                    )
                )
                created += 1
    db.flush()
    return created


def _normalize_variant_names(db) -> int:
    """Names must describe what the package actually contains."""

    renamed = 0
    for product in db.scalars(select(TravelProduct)):
        name = str(product.product_name or "")
        cleaned = name
        if "（" in cleaned and "）" in cleaned:
            head, rest = cleaned.split("（", 1)
            cleaned = (head + rest.split("）", 1)[1]).strip()
        cleaned = cleaned.replace("｜", "·").strip(" ·")
        theme_core = str(product.theme or "").split("·")[0].strip()
        experiences = [row.resource_name for row in product.resources if row.resource_type == "PARTNER_RESOURCE"]
        if theme_core and experiences and not any(theme_core[:2] in str(item) or str(item)[:2] in theme_core for item in experiences):
            # The name no longer matches the content, so describe the content.
            cleaned = "·".join(str(item) for item in experiences[:2])
        elif theme_core:
            cleaned = theme_core
        if cleaned and cleaned != name:
            product.product_name = cleaned
            renamed += 1
    db.flush()
    return renamed

PHOTO_NOTICE = (
    "拍摄时长约 90 分钟；精修 12 张、原片全送；"
    "经典机位：拱宸桥桥面、桥西直街青石板、运河灯影段；"
    "建议穿浅色或纯色服装，妆造可提前 40 分钟到店"
)


def enrich_resource_details(db) -> int:
    """Add room size/bed detail and structured photo-shoot information."""

    updated = 0
    for room in db.scalars(select(RoomInventory)):
        detail = ROOM_DETAIL_BY_TYPE.get(str(room.room_type))
        if not detail:
            continue
        if detail in str(room.features or ""):
            continue
        room.features = f"{str(room.features or '').strip('、')}｜{detail}" if room.features else detail
        updated += 1
    for resource in db.scalars(select(PartnerResource)):
        text = f"{resource.resource_name} {resource.category or ''}"
        if not any(word in text for word in ("旅拍", "摄影", "拍照", "PHOTO", "PHOTO_GRAPH")):
            continue
        if "拍摄时长" in str(resource.booking_notice or ""):
            continue
        resource.booking_notice = PHOTO_NOTICE
        if "摄影师" not in str(resource.description or ""):
            resource.description = f"{str(resource.description or '').strip()} 摄影师会按当天光线调整机位与拍摄顺序。".strip()
        updated += 1
    db.flush()
    return updated


def diversify_party_sizes(db) -> int:
    """Give the catalogue real 4–6 person options, not only 2–3 person packs."""

    updated = 0
    products = list(db.scalars(select(TravelProduct).order_by(TravelProduct.id)).all())
    for index, product in enumerate(products):
        if product.target_crowd == "FAMILY":
            wanted = [3, 4, 5, 6][index % 4]
        elif product.target_crowd == "FRIENDS":
            wanted = [4, 6][index % 2]
        else:
            wanted = product.party_size or 2
        room = db.get(RoomInventory, product.room_inventory_id)
        if room is not None and wanted > int(room.max_guests or 0):
            wanted = max(1, int(room.max_guests))
        if wanted != product.party_size:
            product.party_size = wanted
            updated += 1
    db.flush()
    return updated


def clean_risk_copy(db) -> int:
    """Replace the repeated weather/allergy disclaimer with one short note."""

    updated = 0
    for product in db.scalars(select(TravelProduct)):
        note = "具体场次以购买确认信息为准。"
        if product.risk_message != note:
            product.risk_message = note
            updated += 1
    db.flush()
    return updated


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        extra_rooms = add_extra_room_types(db)
        experiences = enrich_experiences(db)
        resource_details = enrich_resource_details(db)
        variants = create_room_variants(db)
        reviews = seed_reviews(db)
        orders = seed_orders(db)
        copies = refresh_copy(db)
        renames = _rename_products(db)
        variant_renames = _normalize_variant_names(db)
        parties = diversify_party_sizes(db)
        assets = refresh_marketing_assets(db, force=os.environ.get("FORCE_ASSETS") == "1")
        risks = clean_risk_copy(db)
        db.commit()
        print(
            {
                "experiences_added": experiences,
                "extra_room_types_created": extra_rooms,
                "resource_details_updated": resource_details,
                "room_variants_created": variants,
                "reviews_created": reviews,
                "orders_created": orders,
                "products_rewritten": copies,
                "products_renamed": renames,
                "variant_names_normalised": variant_renames,
                "party_sizes_updated": parties,
                "marketing_assets_built": assets,
                "risk_copy_updated": risks,
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
