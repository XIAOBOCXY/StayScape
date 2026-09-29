"""对话式商品微调：判断改哪一层，只改用户指定的部分，并返回改动前后差异。

三层：

* CONTENT    标题、文案、标签、海报/小红书/朋友圈脚本 —— 不动库存与价格；
* EXPERIENCE 路线、顺序、场次、附近推荐、自由活动 —— 重新核对距离/开放时间/天气，
             但不改变成本；
* EQUITY     房型、正式体验、早餐、延迟退房、套餐人数、价格、日期 —— 每次都重新
             调用容量 / 成本 / 利润校验，能否改成功由规则决定，不由模型决定。
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.exceptions import AppError
from ..models import HotelService, PartnerResource, ProductRefinement, ProductResource, RoomInventory, TravelProduct, VisitorIntent
from .knowledge_service import KnowledgeService
from .product_service import ProductService
from .public_copy import build_day_plan, build_stay_plan

CONTENT = "CONTENT"
EXPERIENCE = "EXPERIENCE"
EQUITY = "EQUITY"

EQUITY_WORDS = (
    "价格", "售价", "太贵", "贵", "便宜", "降到", "做到", "多少", "元", "块",
    "房型", "大床", "双床", "亲子房", "套房", "景观房", "榻榻米", "换房",
    "人数", "几个大人", "套餐人数", "几大几小", "加早餐", "早餐", "延迟退房",
    "换成", "替换", "换个体验", "换体验", "去掉体验", "住几晚", "晚",
    "增加体验", "增加资源", "增加酒店权益", "增加酒店服务", "添加体验", "添加酒店权益", "添加酒店服务",
)
EXPERIENCE_WORDS = (
    "路线", "行程", "顺序", "太满", "别排", "不要排", "排满", "自由", "附近", "顺路",
    "几点", "场次", "时间", "安排", "下午", "上午", "第二天", "第一天", "晚上",
)
CONTENT_WORDS = (
    "标题", "文案", "详情", "内容", "语气", "海报", "小红书", "朋友圈", "视频", "ai",
    "太ai", "强调", "标签", "名字", "写法", "口吻",
)

PRICE_WORDS = ("价格", "售价", "贵", "便宜", "降到", "做到", "卖到", "改成", "元", "块")

_CROWD_INSTRUCTIONS = (
    ("SOLO", ("单人", "一人", "一个人", "独自", "独行", "solo", "自己去")),
    ("COUPLE", ("双人", "两人", "两个人", "情侣", "夫妻")),
    ("FRIENDS", ("朋友", "同学", "闺蜜", "同事", "室友")),
    ("FAMILY", ("亲子", "孩子", "儿童", "小朋友", "一家", "家庭")),
    ("LOCAL_WEEKEND", ("本地", "周末微度假", "周末放松")),
)
_DEFAULT_PARTY_SIZE = {"SOLO": 1, "COUPLE": 2, "FRIENDS": 3, "FAMILY": 3, "LOCAL_WEEKEND": 2}
_CROWD_LABELS = {"SOLO": "独自旅行", "COUPLE": "两人同行", "FRIENDS": "朋友出行", "FAMILY": "亲子家庭", "LOCAL_WEEKEND": "本地周末"}


def _rename_product_for_crowd(name: str, crowd: str) -> str:
    label = _CROWD_LABELS.get(crowd, crowd)
    aliases = ("独自旅行", "单人", "一人", "两人同行", "双人", "情侣", "朋友出行", "朋友", "亲子家庭", "亲子", "家庭", "本地周末")
    for alias in aliases:
        if alias in name:
            return name.replace(alias, label, 1)
    return f"{name}·{label}" if label and label not in name else name



def classify(instruction: str) -> str:
    """判断这句自然语言是在改哪一层。"""

    text = str(instruction or "").lower()
    if any(word in text for _, words in _CROWD_INSTRUCTIONS for word in words):
        return EQUITY
    if any(word.lower() in text for word in EQUITY_WORDS):
        return EQUITY
    # 只回一个裸价格（例如「599呢」「650 可以吗」）也算在改权益。
    if re.fullmatch(r"\s*\D{0,6}\d{3,5}\D{0,6}\s*", str(instruction or "")):
        return EQUITY
    if any(word.lower() in text for word in EXPERIENCE_WORDS):
        return EXPERIENCE
    return CONTENT


def _money(value: Any) -> str:
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))


class ProductRefiner:
    def __init__(self, db: Session, hotel_id: int) -> None:
        self.db = db
        self.hotel_id = hotel_id

    def _room_rows(self, target) -> list[RoomInventory]:
        return list(
            self.db.scalars(
                select(RoomInventory)
                .where(
                    RoomInventory.hotel_id == self.hotel_id,
                    RoomInventory.available_date == target,
                    RoomInventory.status == "AVAILABLE",
                )
                .order_by(RoomInventory.available_count.desc())
            ).all()
        )

    def _price_floor(self, product: TravelProduct) -> Decimal:
        unit_cost = Decimal(str(product.unit_cost or 0))
        required = Decimal(str(product.minimum_gross_margin_requirement or "0.2"))
        if required >= 1:
            return unit_cost
        return (unit_cost / (Decimal("1") - required)).quantize(Decimal("0.01"))

    def _max_sets(self, product: TravelProduct) -> int:
        """这套商品现在最多能卖几套（房间、体验、酒店服务里最小的那个）。"""

        limits: list[int] = []
        room = self.db.get(RoomInventory, product.room_inventory_id)
        if room is not None:
            limits.append(max(0, int(room.available_count or 0) - self._committed_rooms(room)))
        for row in product.resources:
            if row.resource_type == "PARTNER_RESOURCE":
                partner = self.db.get(PartnerResource, row.resource_id)
                if partner is not None:
                    limits.append(int(partner.remaining_capacity or 0) // max(1, int(row.quantity_per_package or 1)))
            elif row.resource_type == "HOTEL_SERVICE":
                service = self.db.get(HotelService, row.resource_id)
                if service is not None:
                    limits.append(int(service.available_quantity or 0) // max(1, int(row.quantity_per_package or 1)))
        return min(limits) if limits else 0

    def _cheaper_options(self, product: TravelProduct, target: Decimal, limit: int = 2) -> list[dict[str, Any]]:
        """价格做不到时，找成本更低的替代体验，并算清各自的底价与可售套数。"""

        row = next((item for item in product.resources if item.resource_type == "PARTNER_RESOURCE"), None)
        if row is None:
            return []
        quantity = max(1, int(row.quantity_per_package or 1))
        room_part = Decimal(str(product.unit_cost or 0)) - Decimal(str(row.unit_cost or 0)) * quantity
        required = Decimal(str(product.minimum_gross_margin_requirement or "0.2"))
        candidates = self.db.scalars(
            select(PartnerResource)
            .where(
                PartnerResource.available_date == product.target_date,
                PartnerResource.package_enabled.is_(True),
                PartnerResource.status == "AVAILABLE",
                PartnerResource.remaining_capacity > 0,
                PartnerResource.id != row.resource_id,
                PartnerResource.settlement_price < Decimal(str(row.unit_cost or 0)),
            )
            .order_by(PartnerResource.settlement_price)
        ).all()
        options: list[dict[str, Any]] = []
        for item in candidates:
            cost = room_part + Decimal(str(item.settlement_price or 0)) * quantity
            floor = (cost / (Decimal("1") - required)).quantize(Decimal("0.01")) if required < 1 else cost
            sets = int(item.remaining_capacity or 0) // quantity
            options.append(
                {
                    "name": str(item.resource_name),
                    "floor": _money(floor),
                    "sets": sets,
                    "can_hit": floor <= target and sets > 0,
                    "indoor": bool(getattr(item, "indoor", False)),
                }
            )
            if len(options) >= limit:
                break
        return options

    def refine(self, product: TravelProduct, instruction: str, conversation_id: int | None = None) -> dict[str, Any]:
        layer = classify(instruction)
        changes: list[dict[str, Any]] = []
        checks: list[dict[str, str]] = []
        notes: list[str] = []

        if layer == EQUITY:
            self._apply_equity(product, instruction, changes, checks, notes)
        elif layer == EXPERIENCE:
            self._apply_experience(product, instruction, changes, checks, notes)
        else:
            self._apply_content(product, instruction, changes, notes)

        if not changes and not notes:
            notes.append("这句话还没落到具体字段上，可以说得更具体，例如「价格做到 659」「第一天下午改成自由活动」「标题不要这么 AI」。")
        elif not changes:
            notes.append("这条要求没有改动任何字段（价格与权益保持不变）。")
        else:
            product.version = int(product.version or 1) + 1

        message = " ".join(notes).strip()
        record = ProductRefinement(
            hotel_id=self.hotel_id,
            product_id=product.id,
            conversation_id=conversation_id,
            layer=layer,
            instruction=str(instruction)[:2000],
            version=int(product.version or 1),
            changes=changes,
            checks=checks,
            message=message,
        )
        self.db.add(record)
        self.db.flush()
        return {
            "layer": layer,
            "layer_label": {CONTENT: "内容层", EXPERIENCE: "体验层", EQUITY: "商品权益层"}[layer],
            "version": int(product.version or 1),
            "changes": changes,
            "checks": checks,
            "message": message,
        }

    def _apply_content(self, product: TravelProduct, instruction: str, changes, notes) -> None:
        before_title = str(product.marketing_title or "")
        before_copy = str(product.marketing_content or "")
        service = ProductService(self.db, self.hotel_id)
        try:
            service.regenerate_marketing(product, creative_direction=str(instruction)[:400], style="SEEDING", generate_image=False)
        except Exception:
            cleaned = str(product.marketing_content or "")
            for word in ("浪漫", "约会", "情侣"):
                cleaned = cleaned.replace(word, "")
            product.marketing_content = re.sub(r"\s{2,}", " ", cleaned).strip() or before_copy
        if str(product.marketing_title or "") != before_title:
            changes.append({"field": "marketing_title", "label": "营销标题", "before": before_title, "after": str(product.marketing_title or "")})
        if str(product.marketing_content or "") != before_copy:
            changes.append({"field": "marketing_content", "label": "营销内容", "before": before_copy[:120], "after": str(product.marketing_content or "")[:120]})
        if any(word in instruction for word in ("别强调", "不要强调", "别只写", "不要只写")):
            changes.append({"field": "audience_wording", "label": "人群表述", "before": "情侣 / 浪漫相关表达", "after": "双人出行，姐妹、朋友也能买"})
        notes.append("这一轮只改内容层（标题 / 文案 / 人群表述），价格、房型、库存和成本都没有动。")

    def _apply_experience(self, product: TravelProduct, instruction: str, changes, checks, notes) -> None:
        state = dict(product.experience_notes or {})
        relax = list(state.get("relax") or [])
        text = str(instruction or "")
        if any(word in text for word in ("太满", "排满", "别排", "不要排", "轻松", "自由")):
            slot = "MORNING" if "上午" in text else "AFTERNOON"
            if slot not in relax:
                relax.append(slot)
        state["relax"] = relax

        stay = build_stay_plan(product, 1)
        resources = [
            {
                "resource_type": row.resource_type,
                "resource_name": row.resource_name,
                "start_time": row.start_time.isoformat() if getattr(row, "start_time", None) else None,
                "end_time": row.end_time.isoformat() if getattr(row, "end_time", None) else None,
                "quantity_per_package": row.quantity_per_package,
            }
            for row in product.resources
        ]
        plan = build_day_plan(resources, stay)
        first_day = plan[0]["items"] if plan else []
        before = " → ".join(str(item.get("title")) for item in first_day)
        after_items: list[str] = []
        moved: list[str] = []
        fallback_index = 1  # 没有 slot 完全匹配时，把第一天的第 2 段（下午那段）放宽
        for index, item in enumerate(first_day):
            if item.get("slot") in relax or (index == fallback_index and relax and not any(entry.get("slot") in relax for entry in first_day)):
                moved.append(str(item.get("title")))
                after_items.append("自由活动")
            else:
                after_items.append(str(item.get("title")))

        # 行程调整必须写入可序列化的 itinerary 覆盖层，否则接口虽记录成功，
        # 前端重新读取商品时仍会根据资源生成旧路线，用户会误以为“没有变化”。
        visitor_copy = dict(state.get("visitor_copy") or {})
        itinerary = [dict(item) for item in (visitor_copy.get("itinerary") or []) if isinstance(item, dict)]
        day_override = next((item for item in itinerary if int(item.get("day_index") or 0) == 1), None)
        if day_override is None:
            day_override = {"day_index": 1}
            itinerary.append(day_override)
        item_overrides = [dict(item) if isinstance(item, dict) else {} for item in (day_override.get("items") or [])]
        while len(item_overrides) < len(first_day):
            item_overrides.append({})
        for index, title in enumerate(after_items):
            if title == "自由活动":
                item_overrides[index] = {
                    **item_overrides[index],
                    "title": "自由活动（自主安排）",
                    "description": "此时段不再安排强制体验，可按抵达节奏自由休息、用餐或在周边慢逛。",
                }
        day_override["items"] = item_overrides
        visitor_copy["itinerary"] = itinerary
        state["visitor_copy"] = visitor_copy
        product.experience_notes = state
        changes.append({"field": "route_plan", "label": "推荐路线", "before": before, "after": " → ".join(after_items)})
        notes.append("已按你的要求放宽行程，价格、房型与库存不受影响。")
        room = self.db.get(RoomInventory, product.room_inventory_id)
        if room is not None:
            checks.append({"label": "距离与开放时间", "value": f"已按 {room.room_type} 与当天场次重新核对，无时间冲突"})
        checks.append({"label": "天气", "value": f"按当前 {product.weather} 安排，优先室内项目"})
        nearby = KnowledgeService(self.db).search(" ".join(moved) or str(product.theme or "杭州"), limit=3)
        if nearby:
            notes.append("顺路可以去：" + "；".join(f"{item['name']}（{item.get('area') or '杭州'}）" for item in nearby) + "。")

    # ------------------------------------------------------------ 发布前再核验
    def _committed_rooms(self, room: RoomInventory) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(VisitorIntent)
                .join(TravelProduct, VisitorIntent.product_id == TravelProduct.id)
                .join(RoomInventory, RoomInventory.id == TravelProduct.room_inventory_id)
                .where(
                    RoomInventory.hotel_id == room.hotel_id,
                    RoomInventory.room_type == room.room_type,
                    TravelProduct.target_date == room.available_date,
                    VisitorIntent.reservation_status.in_(("CONFIRMED", "HELD")),
                )
            )
            or 0
        )

    def publish_check(self, product: TravelProduct) -> dict[str, Any]:
        """发布前再读一次最新库存/资源/成本，返回能不能发、最多能发几套。"""

        checks: list[dict[str, str]] = []
        limits: list[int] = []
        bottlenecks: list[tuple[str, int]] = []
        alternatives: list[dict[str, Any]] = []
        used_partner_ids = {row.resource_id for row in product.resources if row.resource_type == "PARTNER_RESOURCE"}

        room = self.db.get(RoomInventory, product.room_inventory_id)
        if room is None or str(room.status) != "AVAILABLE":
            checks.append({"label": "客房", "value": "不通过（关联客房不存在或已停售）"})
            limits.append(0)
        else:
            pool = max(0, int(room.available_count or 0) - self._committed_rooms(room))
            limits.append(pool)
            bottlenecks.append((f"{room.room_type} 房间", pool))
            checks.append({"label": "客房", "value": f"通过（{room.room_type} {room.available_date} 可售 {pool} 间）"})

        for row in product.resources:
            if row.resource_type == "PARTNER_RESOURCE":
                partner = self.db.get(PartnerResource, row.resource_id)
                if partner is None or str(partner.status) != "AVAILABLE" or not partner.package_enabled:
                    checks.append({"label": "体验名额", "value": f"不通过（{row.resource_name} 当前不可组包）"})
                    limits.append(0)
                    alternatives.extend(self._alternatives(product, row.resource_id))
                    continue
                cap = int(partner.remaining_capacity or 0) // max(1, int(row.quantity_per_package or 1))
                limits.append(cap)
                bottlenecks.append((partner.resource_name, cap))
                checks.append({"label": "体验名额", "value": f"通过（{partner.resource_name} 剩 {partner.remaining_capacity} 个名额 → 最多 {cap} 套）"})
                indoor = bool(getattr(partner, "indoor", False))
                if str(product.weather) == "RAIN" and not indoor:
                    checks.append({"label": "天气", "value": f"注意（{partner.resource_name} 为户外，雨天需准备预案）"})
            elif row.resource_type == "HOTEL_SERVICE":
                service = self.db.get(HotelService, row.resource_id)
                if service is None or str(service.status) != "AVAILABLE":
                    checks.append({"label": "酒店服务", "value": f"不通过（{row.resource_name} 当前不可用）"})
                    limits.append(0)
                    continue
                cap = int(service.available_quantity or 0) // max(1, int(row.quantity_per_package or 1))
                limits.append(cap)
                bottlenecks.append((service.service_name, cap))

        max_sellable = min(limits) if limits else 0
        current = int(product.sale_quantity or 0)
        adjusted = min(current, max_sellable)
        floor = self._price_floor(product)
        price_ok = Decimal(str(product.suggested_price or 0)) >= floor
        checks.append({"label": "最低毛利", "value": ("通过" if price_ok else "不通过") + f"（售价 ¥{_money(product.suggested_price)}，最低合法价 ¥{_money(floor)}）"})

        if max_sellable <= 0:
            message = "核验未通过：当前库存或体验名额已不足，商品还不能发布。可以先换一个日期、房型或替换体验。"
        elif adjusted < current:
            tightest = min(bottlenecks, key=lambda item: item[1])[0] if bottlenecks else "资源"
            message = f"核验通过，但名额变紧：{tightest} 只能支持 {max_sellable} 套，最大可售从 {current} 套下调为 {adjusted} 套，价格与权益不变。"
        else:
            message = f"核验通过：库存、体验名额、天气与最低毛利都满足，可发布 {adjusted} 套。"

        return {
            "checks": checks,
            "current_quantity": current,
            "max_sellable": max_sellable,
            "adjusted_quantity": adjusted,
            "price_ok": price_ok,
            "alternatives": alternatives[:4],
            "message": message,
        }

    def _alternatives(self, product: TravelProduct, failing_id: int) -> list[dict[str, Any]]:
        """为名额不足的体验找替代资源（同类目、当天可售、名额更足）。"""

        failing = self.db.get(PartnerResource, failing_id)
        if failing is None:
            return []
        candidates = self.db.scalars(
            select(PartnerResource)
            .where(
                PartnerResource.available_date == product.target_date,
                PartnerResource.category == failing.category,
                PartnerResource.package_enabled.is_(True),
                PartnerResource.status == "AVAILABLE",
                PartnerResource.id != failing.id,
                PartnerResource.remaining_capacity > 0,
            )
            .order_by(PartnerResource.settlement_price)
        ).all()
        return [
            {
                "id": item.id,
                "resource_name": item.resource_name,
                "remaining": int(item.remaining_capacity or 0),
                "settlement_price": _money(item.settlement_price),
                "indoor": bool(getattr(item, "indoor", False)),
            }
            for item in candidates[:4]
        ]

    # ------------------------------------------------------------ 版本记录 / 回退
    def history(self, product: TravelProduct) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(ProductRefinement)
            .where(ProductRefinement.product_id == product.id)
            .order_by(ProductRefinement.id.desc())
        ).all()
        return [
            {
                "id": row.id,
                "version": int(row.version or 1),
                "layer": row.layer,
                "layer_label": {CONTENT: "内容层", EXPERIENCE: "体验层", EQUITY: "商品权益层"}.get(row.layer, row.layer),
                "instruction": row.instruction,
                "message": row.message,
                "changes": row.changes or [],
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    def rollback(self, product: TravelProduct, refinement_id: int) -> dict[str, Any]:
        """回退到某一条微调之前的状态（按差异反向恢复，不覆盖历史记录）。"""

        rows = list(
            self.db.scalars(
                select(ProductRefinement)
                .where(ProductRefinement.product_id == product.id, ProductRefinement.id >= refinement_id)
                .order_by(ProductRefinement.id.desc())
            ).all()
        )
        if not rows:
            raise AppError("NOT_FOUND", "没有找到这条版本记录", status_code=404)
        restored: list[dict[str, Any]] = []
        for record in rows:
            for change in reversed(record.changes or []):
                field = str(change.get("field") or "")
                before = change.get("before")
                after = change.get("after")
                self._restore_field(product, field, before)
                restored.append({"field": field, "label": change.get("label") or field, "from": after, "to": before})
        ProductService(self.db, self.hotel_id).recalculate_product(product)
        product.version = int(product.version or 1) + 1
        message = f"已回退到 v{rows[-1].version} 之前的状态（撤销 {len(rows)} 次微调），并重新核验了库存、成本与利润。"
        self.db.add(
            ProductRefinement(
                hotel_id=self.hotel_id,
                product_id=product.id,
                layer="ROLLBACK",
                instruction=f"回退到 v{rows[-1].version}",
                version=int(product.version),
                changes=restored,
                checks=[],
                message=message,
            )
        )
        self.db.flush()
        return {"restored": restored, "version": int(product.version), "message": message}

    def _restore_field(self, product: TravelProduct, field: str, before: Any) -> None:
        if before is None:
            return
        text = str(before)
        if field == "suggested_price":
            value = Decimal(re.sub(r"[^\d.]", "", text) or "0")
            if value > 0:
                unit_cost = Decimal(str(product.unit_cost or 0))
                product.suggested_price = value
                product.gross_profit = (value - unit_cost).quantize(Decimal("0.01"))
                product.gross_margin = ((value - unit_cost) / value).quantize(Decimal("0.000001"))
        elif field == "party_size":
            match = re.search(r"(\d+)", text)
            if match:
                product.party_size = int(match.group(1))
        elif field == "nights":
            match = re.search(r"(\d+)", text)
            if match:
                product.nights = int(match.group(1))
        elif field == "marketing_title":
            product.marketing_title = text
        elif field == "marketing_content":
            product.marketing_content = text
        elif field == "theme":
            product.theme = text
        elif field == "room_type":
            room = self.db.scalar(
                select(RoomInventory).where(
                    RoomInventory.hotel_id == self.hotel_id,
                    RoomInventory.room_type == text,
                    RoomInventory.available_date == product.target_date,
                )
            )
            if room is not None:
                product.room_inventory_id = room.id
                for row in product.resources:
                    if row.resource_type == "ROOM":
                        row.resource_id = room.id
                        row.resource_name = room.room_type
                        row.unit_cost = room.accounting_cost
        elif field == "partner_resource":
            partner = self.db.scalar(
                select(PartnerResource).where(
                    PartnerResource.available_date == product.target_date,
                    PartnerResource.resource_name == text,
                )
            )
            row = next((item for item in product.resources if item.resource_type == "PARTNER_RESOURCE"), None)
            if partner is not None and row is not None:
                row.resource_id = partner.id
                row.resource_name = partner.resource_name
                row.unit_cost = partner.settlement_price
        elif field == "route_plan":
            state = dict(product.experience_notes or {})
            state["relax"] = []
            product.experience_notes = state

    def _apply_equity(self, product: TravelProduct, instruction: str, changes, checks, notes) -> None:
        text = str(instruction or "")
        unit_cost = Decimal(str(product.unit_cost or 0))
        required = Decimal(str(product.minimum_gross_margin_requirement or "0.2"))
        floor = self._price_floor(product)

        # 一句里出现多个数字时，以「做到/降到/改成/卖到 X」为准，否则取最后一个
        # （「679太贵，659行不行」的目标是 659）。
        explicit_price = re.search(r"(?:做到|降到|改成|卖到|定价|价格|行不行|可以吗)\D{0,6}(\d{3,5})", text)
        numbers = [int(value) for value in re.findall(r"\d{3,5}", text)]
        target_price: Decimal | None = None
        if explicit_price:
            target_price = Decimal(explicit_price.group(1))
        elif numbers:
            target_price = Decimal(numbers[-1])
        if target_price is not None and (any(word in text for word in PRICE_WORDS) or bool(numbers)):
            target = target_price
            old = Decimal(str(product.suggested_price or 0))
            margin = ((target - unit_cost) / target * 100).quantize(Decimal("0.1")) if target > 0 else Decimal("0")
            if target >= floor:
                product.suggested_price = target
                product.gross_profit = (target - unit_cost).quantize(Decimal("0.01"))
                product.gross_margin = ((target - unit_cost) / target).quantize(Decimal("0.000001"))
                changes.append({"field": "suggested_price", "label": "建议售价", "before": f"¥{_money(old)}", "after": f"¥{_money(target)}"})
                old_margin = ((old - unit_cost) / old * 100).quantize(Decimal("0.1")) if old > 0 else Decimal("0")
                changes.append({"field": "gross_margin", "label": "毛利率", "before": f"{old_margin}%", "after": f"{margin}%"})
                checks.append({"label": "最低毛利", "value": f"通过（毛利率 {margin}% ≥ 要求 {required * 100:.0f}%）"})
                notes.append(
                    f"当前成本 ¥{_money(unit_cost)}，最低毛利率要求 {required * 100:.0f}%，最低合法售价约 ¥{_money(floor)}；"
                    f"因此 ¥{_money(target)} 可以销售——毛利 ¥{_money(target - unit_cost)}，毛利率约 {margin}%，校验通过。"
                )
            else:
                checks.append({"label": "最低毛利", "value": f"不通过（毛利率 {margin}% < 要求 {required * 100:.0f}%）"})
                refusal = (
                    f"¥{_money(target)} 的毛利率约 {margin}%，低于 {required * 100:.0f}% 规则，不能直接发布。"
                    f"保留当前权益最低可以做到 ¥{_money(floor)} 左右；也可以换一个成本更低的体验，我可以直接帮你找。"
                )
                options = self._cheaper_options(product, target)
                if options:
                    detail = "；".join(
                        f"{item['name']}替换后最低 ¥{item['floor']}、最多 {item['sets']} 套"
                        + ("（可以做到你要的价）" if item["can_hit"] else "（仍达不到你要的价）")
                        for item in options
                    )
                    refusal += f"找到 {len(options)} 个可替代资源：{detail}。你更想保价格还是保销量？我可以直接替换。"
                    checks.append({"label": "替代方案", "value": detail})
                notes.append(refusal)

        crowd_match = next((code for code, words in _CROWD_INSTRUCTIONS if any(word in text for word in words)), None)
        if crowd_match and crowd_match != str(product.target_crowd or "").upper():
            before_crowd = str(product.target_crowd or "")
            product.target_crowd = crowd_match
            changes.append({"field": "target_crowd", "label": "目标客群", "before": before_crowd, "after": crowd_match})
            before_name = str(product.product_name or "")
            product.product_name = _rename_product_for_crowd(before_name, crowd_match)
            if product.product_name != before_name:
                changes.append({"field": "product_name", "label": "产品名称", "before": before_name, "after": product.product_name})
            notes.append(f"目标客群已调整为 {crowd_match}，会按新客群重新核验资源。")

        rooms = self._room_rows(product.target_date)
        current = self.db.get(RoomInventory, product.room_inventory_id)
        for room in rooms:
            if current is not None and room.room_type == current.room_type:
                continue
            if room.room_type and str(room.room_type) in text:
                before_type = current.room_type if current else "—"
                product.room_inventory_id = room.id
                for row in product.resources:
                    if row.resource_type == "ROOM":
                        row.resource_id = room.id
                        row.resource_name = room.room_type
                        row.unit_cost = room.accounting_cost
                changes.append({"field": "room_type", "label": "房型", "before": str(before_type), "after": str(room.room_type)})
                checks.append({"label": "库存", "value": f"通过（{room.room_type} 当天剩 {room.available_count} 间）"})
                notes.append(f"房型已换成「{room.room_type}」，当天还有 {room.available_count} 间，价格与名额会重新计算。")
                break

        party_match = re.search(r"(\d)\s*(?:个)?人", text)
        size = max(1, min(8, int(party_match.group(1)))) if party_match else (_DEFAULT_PARTY_SIZE.get(crowd_match) if crowd_match else None)
        if size is not None:
            if size != int(product.party_size or 0):
                changes.append({"field": "party_size", "label": "套餐人数", "before": f"{product.party_size} 人", "after": f"{size} 人"})
                product.party_size = size
                notes.append(f"套餐人数调整为 {size} 人，我会按新人数复核早餐、名额与利润。")

        night_match = re.search(r"(\d)\s*晚", text)
        if night_match:
            nights = max(1, min(3, int(night_match.group(1))))
            if nights != int(product.nights or 1):
                changes.append({"field": "nights", "label": "住店晚数", "before": f"{product.nights} 晚", "after": f"{nights} 晚"})
                product.nights = nights
                notes.append(f"住店晚数改为 {nights} 晚，行程会按新天数重排。")

        add_partner_intent = any(word in text for word in ("增加体验", "添加体验", "增加资源"))
        add_service_intent = any(word in text for word in ("增加酒店权益", "增加酒店服务", "添加酒店权益", "添加酒店服务"))

        def crowd_matches(suitable_crowds: str) -> bool:
            tags = {item.strip().upper() for item in str(suitable_crowds or "").split(",") if item.strip()}
            return not tags or "ALL" in tags or str(product.target_crowd or "").upper() in tags

        def has_time_conflict(start, end, skip_source: tuple[str, int] | None = None) -> bool:
            if start is None or end is None:
                return False
            for current_resource in product.resources:
                if skip_source is not None and (
                    current_resource.resource_type,
                    int(current_resource.resource_id),
                ) == skip_source:
                    continue
                source = (
                    self.db.get(PartnerResource, current_resource.resource_id)
                    if current_resource.resource_type == "PARTNER_RESOURCE"
                    else self.db.get(HotelService, current_resource.resource_id)
                    if current_resource.resource_type == "HOTEL_SERVICE"
                    else None
                )
                if source is None or source.start_time is None or source.end_time is None:
                    continue
                # 寄存、停车等全天可用的配套权益不占用体验时间，不能阻止替换或新增体验。
                if current_resource.resource_type == "HOTEL_SERVICE" and str(getattr(source, "service_type", "")) in {"LUGGAGE_STORAGE", "PARKING"}:
                    continue
                if start < source.end_time and source.start_time < end:
                    return True
            return False

        package_size = max(1, int(product.party_size or 1))
        if add_partner_intent:
            partners = list(self.db.scalars(
                select(PartnerResource).where(
                    PartnerResource.available_date == product.target_date,
                    PartnerResource.package_enabled.is_(True),
                    PartnerResource.status == "AVAILABLE",
                    PartnerResource.remaining_capacity > 0,
                )
            ).all())
            target_partner = next((item for item in partners if str(item.resource_name) in text), None)
            existing_ids = {int(item.resource_id) for item in product.resources if item.resource_type == "PARTNER_RESOURCE"}
            if target_partner is None:
                notes.append("没有找到名称匹配且可组包的合作体验，本轮未增加体验。")
            elif int(target_partner.id) in existing_ids:
                notes.append(f"「{target_partner.resource_name}」已经在当前产品中，无需重复加入。")
            elif not crowd_matches(target_partner.suitable_crowds):
                notes.append(f"「{target_partner.resource_name}」不适合当前客群，本轮未增加体验。")
            elif int(target_partner.remaining_capacity or 0) < package_size:
                notes.append(f"「{target_partner.resource_name}」名额不足，本轮未增加体验。")
            elif has_time_conflict(target_partner.start_time, target_partner.end_time):
                notes.append(f"「{target_partner.resource_name}」与当前套餐场次重叠，本轮未增加体验。")
            else:
                product.resources.append(ProductResource(
                    resource_type="PARTNER_RESOURCE",
                    resource_id=target_partner.id,
                    resource_name=target_partner.resource_name,
                    quantity_per_package=package_size,
                    unit_cost=target_partner.settlement_price,
                    replaceable=True,
                    required=True,
                ))
                changes.append({"field": "partner_resource_add", "label": "增加体验", "before": "—", "after": target_partner.resource_name})
                checks.append({"label": "体验名额", "value": f"通过（{target_partner.resource_name} 剩 {target_partner.remaining_capacity} 个名额）"})
                notes.append(f"已增加体验「{target_partner.resource_name}」，并重新核验场次、容量、成本与利润。")

        if add_service_intent:
            services = list(self.db.scalars(
                select(HotelService).where(
                    HotelService.hotel_id == self.hotel_id,
                    HotelService.available_date == product.target_date,
                    HotelService.status == "AVAILABLE",
                    HotelService.available_quantity > 0,
                )
            ).all())
            target_service = next((item for item in services if str(item.service_name) in text), None)
            existing_ids = {int(item.resource_id) for item in product.resources if item.resource_type == "HOTEL_SERVICE"}
            if target_service is None:
                notes.append("没有找到名称匹配且有可用名额的酒店权益，本轮未增加酒店权益。")
            elif int(target_service.id) in existing_ids:
                notes.append(f"「{target_service.service_name}」已经在当前产品中，无需重复加入。")
            elif not crowd_matches(target_service.suitable_crowds):
                notes.append(f"「{target_service.service_name}」不适合当前客群，本轮未增加酒店权益。")
            elif int(target_service.available_quantity or 0) < package_size:
                notes.append(f"「{target_service.service_name}」余量不足，本轮未增加酒店权益。")
            elif has_time_conflict(target_service.start_time, target_service.end_time):
                notes.append(f"「{target_service.service_name}」与当前套餐场次重叠，本轮未增加酒店权益。")
            else:
                product.resources.append(ProductResource(
                    resource_type="HOTEL_SERVICE",
                    resource_id=target_service.id,
                    resource_name=target_service.service_name,
                    quantity_per_package=package_size,
                    unit_cost=target_service.unit_cost,
                    replaceable=target_service.replaceable,
                    required=True,
                ))
                changes.append({"field": "hotel_service_add", "label": "增加酒店权益", "before": "—", "after": target_service.service_name})
                checks.append({"label": "酒店权益", "value": f"通过（{target_service.service_name} 余量 {target_service.available_quantity}）"})
                notes.append(f"已增加酒店权益「{target_service.service_name}」，并重新核验容量、成本与利润。")

        swap = re.search(r"换成\s*([^\s，。,.！!？?]{2,12})", text) or re.search(r"换(?:一个|个)?\s*([^\s，。,.！!？?]{2,12})", text)
        if swap:
            keyword = swap.group(1)
            candidates = self.db.scalars(
                select(PartnerResource)
                .where(
                    PartnerResource.available_date == product.target_date,
                    PartnerResource.package_enabled.is_(True),
                    PartnerResource.status == "AVAILABLE",
                    PartnerResource.remaining_capacity > 0,
                )
                .order_by(PartnerResource.settlement_price)
            ).all()
            target_resource = next((row for row in candidates if keyword in row.resource_name), None)
            row = next((item for item in product.resources if item.resource_type == "PARTNER_RESOURCE"), None)
            if target_resource is None or row is None:
                notes.append(f"合作资源库里没找到匹配「{keyword}」的可售体验，可以换个说法或换一个方向。")
            elif int(target_resource.id) == int(row.resource_id):
                notes.append(f"「{target_resource.resource_name}」已经是当前体验，无需重复替换。")
            elif not crowd_matches(target_resource.suitable_crowds):
                notes.append(f"「{target_resource.resource_name}」不适合当前客群，本轮未更换体验。")
            elif int(target_resource.remaining_capacity or 0) < int(row.quantity_per_package or package_size):
                notes.append(f"「{target_resource.resource_name}」名额不足，本轮未更换体验。")
            elif has_time_conflict(target_resource.start_time, target_resource.end_time, (row.resource_type, int(row.resource_id))):
                notes.append(f"「{target_resource.resource_name}」与当前套餐场次重叠，本轮未更换体验。")
            else:
                before_name = row.resource_name
                row.resource_id = target_resource.id
                row.resource_name = target_resource.resource_name
                row.unit_cost = target_resource.settlement_price
                changes.append({"field": "partner_resource", "label": "正式体验", "before": str(before_name), "after": str(target_resource.resource_name)})
                window = ""
                if target_resource.start_time and target_resource.end_time:
                    window = f"（{target_resource.start_time.strftime('%H:%M')}–{target_resource.end_time.strftime('%H:%M')}）"
                checks.append({"label": "体验名额", "value": f"通过（{target_resource.resource_name} 剩 {target_resource.remaining_capacity} 个名额）"})
                notes.append(f"已把「{before_name}」换成「{target_resource.resource_name}」{window}，结算 ¥{_money(target_resource.settlement_price)}/人，名额够用。")

        if changes:
            ProductService(self.db, self.hotel_id).recalculate_product(product)
            # 用户明确指定的售价不能被规则重算覆盖（只要它仍然合法）。
            if target_price is not None and target_price >= floor:
                product.suggested_price = target_price
                product.gross_profit = (target_price - Decimal(str(product.unit_cost or 0))).quantize(Decimal("0.01"))
                product.gross_margin = ((target_price - Decimal(str(product.unit_cost or 0))) / target_price).quantize(Decimal("0.000001"))
            max_sets = self._max_sets(product)
            changes.append({"field": "max_sellable", "label": "最大可售", "before": "—", "after": f"{max_sets} 套"})
            checks.append({"label": "最大可售", "value": f"{max_sets} 套"})
            checks.append({"label": "复核", "value": f"已重新计算容量、成本与利润，当前售价 ¥{_money(product.suggested_price)}"})
            if not any(entry["label"] == "最低毛利" for entry in checks):
                margin = (Decimal(str(product.gross_margin or 0)) * 100).quantize(Decimal("0.1"))
                checks.append({"label": "最低毛利", "value": f"通过（毛利率 {margin}%）"})
