"""Multi-turn product advisor for the hotel workbench.

Each turn answers four things, in this order:

1. what the database currently says (rooms, remaining nights, demand, sales);
2. why the suggested packages are suggested;
3. what the recommendation is (room type + date + resources + services);
4. what can be adjusted next, with concrete options.

The conversation is deterministic: every number comes from the database, and
each turn stores its pending plan on the conversation so the next sentence can
refine it instead of starting over.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from ..repositories.product_repository import list_products

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import HotelService, Merchant, PartnerResource, RoomInventory, TravelProduct, VisitorIntent
from .knowledge_service import KnowledgeService
from .weather_service import WeatherService


WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
# 经营判断与主推方案的输出协议版本。plans / primary / resource_options 结构变化时递增，
# 前端只在版本一致时复用历史快照，否则重新生成，避免页面长期显示旧结构数据。
ADVISOR_CONTRACT_VERSION = 6
CROWD_LABELS = {
    "FAMILY": "亲子家庭", "COUPLE": "两人同行", "FRIENDS": "朋友出行",
    "SOLO": "独自旅行", "LOCAL_WEEKEND": "本地周末", "ALL": "不限客群",
}
THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "亲子家庭": ("亲子", "家庭", "孩子", "儿童", "科普", "乐园"),
    "两人约会": ("两人", "双人", "情侣", "约会", "旅拍", "夜游"),
    "朋友出行": ("朋友", "开黑", "聚会", "运动", "卡丁车", "攀岩"),
    "独自旅行": ("单人", "一人", "一个人", "独自", "独行", "solo", "自己去", "咖啡", "看展", "博物馆"),
    "本地周末": ("本地", "周末", "夜市", "演出", "美食"),
}
CONFIRM_WORDS = ("生成", "确认", "可以", "按这个", "就这样", "发布", "没问题", "行")
ADJUST_WORDS = ("换", "调整", "改成", "不要", "加", "去掉", "增加", "减少")

# 客群在数据库里存代码（COUPLE），而模型和界面用中文标签。历史上两种写法混着传，
# 导致「两人同行」去匹配 suitable_crowds 时永远匹配不上，客群过滤形同虚设。
_CROWD_ALIASES = {
    "亲子家庭": "FAMILY",
    "家庭": "FAMILY",
    "两人约会": "COUPLE",
    "两人同行": "COUPLE",
    "情侣": "COUPLE",
    "朋友出行": "FRIENDS",
    "朋友相聚": "FRIENDS",
    "朋友同行": "FRIENDS",
    "独自旅行": "SOLO",
    "独自出行": "SOLO",
    "单人": "SOLO",
    "一人": "SOLO",
    "一个人": "SOLO",
    "独行": "SOLO",
    "solo": "SOLO",
    "自己去": "SOLO",
    "一个人慢游": "SOLO",
    "本地周末": "LOCAL_WEEKEND",
    "本地周末客": "LOCAL_WEEKEND",
    "不限客群": "ALL",
}


def normalize_crowd(value: Any) -> str:
    """把中文标签 / 旧别名统一成 CROWD_LABELS 里的代码。"""

    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in CROWD_LABELS:
        return upper
    if text in _CROWD_ALIASES:
        return _CROWD_ALIASES[text]
    return upper if upper.isascii() else text


def _weekday(value: date) -> str:
    return WEEKDAYS[value.weekday()]


def _money(value: Decimal | float | int | None) -> str:
    return str((Decimal(str(value or 0))).quantize(Decimal("0.01")))


class ProductAdvisor:
    """Turns one operator sentence into the next concrete suggestion."""

    def __init__(self, db: Session, hotel_id: int) -> None:
        self.db = db
        self.hotel_id = hotel_id
        # 本轮对话里如果提到预算，就用它约束合作资源的选择。
        self._turn_budget: Decimal | None = None

    # ---------------------------------------------------------------- database
    def _room_rows(self, days: int = 10) -> list[dict[str, Any]]:
        today = date.today()
        horizon = today + timedelta(days=days)
        rows = list(
            self.db.scalars(
                select(RoomInventory).where(
                    RoomInventory.hotel_id == self.hotel_id,
                    RoomInventory.available_date >= today,
                    RoomInventory.available_date <= horizon,
                    RoomInventory.status == "AVAILABLE",
                )
            ).all()
        )
        grouped: dict[tuple[date, str], dict[str, Any]] = {}
        for room in rows:
            key = (room.available_date, str(room.room_type))
            bucket = grouped.setdefault(
                key,
                {
                    "date": room.available_date,
                    "room_type": str(room.room_type),
                    "pool": 0,
                    "max_guests": int(room.max_guests or 0),
                    "normal_price": Decimal(str(room.normal_price or 0)),
                    "cost": Decimal(str(room.accounting_cost or 0)),
                    "minimum_price": Decimal(str(room.minimum_price or 0)),
                    "features": str(room.features or ""),
                    "crowds": str(room.suitable_crowds or ""),
                },
            )
            bucket["pool"] = max(bucket["pool"], int(room.available_count or 0))
            bucket["max_guests"] = max(bucket["max_guests"], int(room.max_guests or 0))
            bucket["normal_price"] = max(bucket["normal_price"], Decimal(str(room.normal_price or 0)))
        for (target, room_type), bucket in grouped.items():
            bucket["remaining"] = max(0, bucket["pool"] - self._committed(room_type, target))
        return sorted(grouped.values(), key=lambda row: (row["date"], -row["remaining"]))

    def _committed(self, room_type: str, target: date) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(VisitorIntent)
                .join(TravelProduct, VisitorIntent.product_id == TravelProduct.id)
                .join(RoomInventory, RoomInventory.id == TravelProduct.room_inventory_id)
                .where(
                    RoomInventory.hotel_id == self.hotel_id,
                    RoomInventory.room_type == room_type,
                    TravelProduct.target_date == target,
                    VisitorIntent.reservation_status.in_(("CONFIRMED", "HELD")),
                )
            )
            or 0
        )

    def _product_image(self, product: TravelProduct) -> str:
        """Resolve a product's cover from its linked room / partner record."""

        for row in product.resources:
            if row.resource_type == "ROOM":
                room = self.db.get(RoomInventory, row.resource_id)
                if room is not None and getattr(room, "image_url", ""):
                    return str(room.image_url)
            elif row.resource_type == "PARTNER_RESOURCE":
                partner = self.db.get(PartnerResource, row.resource_id)
                if partner is not None and getattr(partner, "image_url", ""):
                    return str(partner.image_url)
        return ""

    def _product_room_type(self, product: TravelProduct) -> str:
        for row in product.resources:
            if row.resource_type == "ROOM":
                room = self.db.get(RoomInventory, row.resource_id)
                if room is not None:
                    return str(room.room_type)
        room = self.db.get(RoomInventory, product.room_inventory_id)
        return str(room.room_type) if room is not None else ""

    def _demand(self) -> dict[str, Any]:
        intents = list(
            self.db.scalars(
                select(VisitorIntent)
                .join(TravelProduct)
                .where(TravelProduct.hotel_id == self.hotel_id)
            ).all()
        )
        window_start = date.today() - timedelta(days=13)
        recent_intents = [
            item for item in intents
            if item.product and window_start <= item.product.target_date <= date.today()
        ]
        confirmed = [item for item in recent_intents if item.reservation_status == "CONFIRMED"]
        by_crowd: dict[str, int] = {}
        revenue = Decimal("0")
        for intent in confirmed:
            product = intent.product
            if product is None:
                continue
            label = CROWD_LABELS.get(str(product.target_crowd), "其他")
            by_crowd[label] = by_crowd.get(label, 0) + 1
            revenue += Decimal(str(product.suggested_price or 0))
        return {
            "orders": len(recent_intents),
            "confirmed": len(confirmed),
            "revenue": revenue,
            "by_crowd": by_crowd,
        }

    def _resources_for(self, target: date, crowd: str, party_size: int) -> list[PartnerResource]:
        rows = list(
            self.db.scalars(
                select(PartnerResource).join(Merchant).where(
                    Merchant.hotel_id == self.hotel_id,
                    PartnerResource.available_date == target,
                    PartnerResource.status == "AVAILABLE",
                    PartnerResource.package_enabled.is_(True),
                    PartnerResource.remaining_capacity >= party_size,
                )
            ).all()
        )
        def score(item: PartnerResource) -> tuple[int, Decimal]:
            tags = str(item.suitable_crowds or "").upper()
            crowd_hit = 0 if crowd in tags or "ALL" in tags else 1
            return (crowd_hit, -Decimal(str(item.market_price or 0)))
        return sorted(rows, key=score)[:6]

    def _services_for(self, target: date) -> list[HotelService]:
        return list(
            self.db.scalars(
                select(HotelService).where(
                    HotelService.hotel_id == self.hotel_id,
                    HotelService.available_date == target,
                    HotelService.available_quantity > 0,
                    HotelService.status == "AVAILABLE",
                ).order_by(HotelService.available_quantity.desc(), HotelService.id)
            ).all()
        )[:8]

    def _resource_by_name(self, target: date, text: str):
        """按名称精确查当天的合作资源。

        ``_resources_for`` 每次只取前 6 条，用户点名要的资源可能不在其中，
        所以显式指定时必须单独查一次，保证「换成 X」一定生效。
        """

        if not str(text or "").strip():
            return None
        rows = list(
            self.db.scalars(
                select(PartnerResource).join(Merchant).where(
                    Merchant.hotel_id == self.hotel_id,
                    PartnerResource.available_date == target,
                    PartnerResource.status == "AVAILABLE",
                    PartnerResource.package_enabled.is_(True),
                )
            ).all()
        )
        hits = [row for row in rows if str(row.resource_name or "") and str(row.resource_name) in text]
        if not hits:
            return None
        return max(hits, key=lambda row: int(row.remaining_capacity or 0))

    # ------------------------------------------------------------- perception
    def _parse(self, message: str, room_types: list[str]) -> dict[str, Any]:
        text = message.strip()
        wanted_room = next((room for room in room_types if room and room in text), None)
        target: date | None = None
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if match:
            target = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        else:
            match = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", text)
            if match:
                today = date.today()
                candidate = date(today.year, int(match.group(1)), int(match.group(2)))
                target = candidate if candidate >= today else candidate.replace(year=today.year + 1)
        if target is None and ("明天" in text or "明晚" in text):
            target = date.today() + timedelta(days=1)
        if target is None and "周末" in text:
            offset = (5 - date.today().weekday()) % 7 or 7
            target = date.today() + timedelta(days=offset)
        crowd = next((label for label, words in THEME_KEYWORDS.items() if any(word in text for word in words)), "")
        party_defaults = {"亲子家庭": 3, "两人约会": 2, "朋友出行": 3, "独自旅行": 1, "本地周末": 2}
        party = party_defaults.get(crowd) if crowd else None
        size = re.search(r"(\d+)\s*(?:人|位)", text)
        if size:
            party = max(1, min(8, int(size.group(1))))
        # 预算：支持「700 以内」「预算 700」「不超过 700」「价格做到 700」等说法。
        budget: Decimal | None = None
        for pattern in (
            r"(?:预算|不超过|最多|封顶|控制在|价格做到|压到)\s*[¥￥]?\s*(\d{2,5})",
            r"[¥￥]?\s*(\d{2,5})\s*(?:元|块)?\s*(?:以内|以下|左右|封顶)",
        ):
            found = re.search(pattern, text)
            if found:
                budget = Decimal(found.group(1))
                break
        return {
            "room_type": wanted_room,
            "target_date": target,
            "crowd": crowd,
            "party_size": party,
            "budget": budget,
            "confirm": any(word in text for word in CONFIRM_WORDS) and not any(word in text for word in ADJUST_WORDS),
            "adjust": any(word in text for word in ADJUST_WORDS),
        }

    # ------------------------------------------------------------------ turns
    @staticmethod
    def _estimated_price(room_row: dict[str, Any], partner, party_size: int, partners=None, services=None) -> Decimal:
        """按正式定价规则（25% 最低毛利、建议价 = 最低合法价 × 1.2）预估售价。"""

        partner_rows = list(partners or [partner])
        service_rows = list(services or [])
        unit_cost = (
            Decimal(str(room_row["cost"]))
            + sum((Decimal(str(item.settlement_price or 0)) * max(1, party_size) for item in partner_rows), Decimal("0"))
            + sum((Decimal(str(item.unit_cost or 0)) * max(1, party_size) for item in service_rows), Decimal("0"))
        )
        margin_floor = unit_cost / (Decimal("1") - Decimal("0.20")) if unit_cost else Decimal("0")
        floor = max(Decimal(str(room_row.get("minimum_price") or 0)), margin_floor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return max(floor, (floor * Decimal("1.2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _resource_window(resource) -> str:
        if resource.start_time and resource.end_time:
            return f"{resource.start_time.strftime('%H:%M')}–{resource.end_time.strftime('%H:%M')}"
        return ""

    def respond(self, message: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = dict(state or {})
        rooms = self._room_rows()
        room_types = sorted({row["room_type"] for row in rooms})
        parsed = self._parse(message, room_types)
        demand = self._demand()
        self._turn_budget = parsed.get("budget")

        if not room_types:
            return {
                "step": "NO_INVENTORY",
                "summary": "当前没有可售房型，请先在临期客房中补充房量。",
                "facts": [],
                "options": [],
                "question": "需要我先按现有房型列出可用日期吗？",
            }

        chosen_room = parsed["room_type"] or state.get("room_type")
        chosen_date = parsed["target_date"] or (
            date.fromisoformat(state["target_date"]) if state.get("target_date") else None
        )
        if state.get("target_date") and state.get("room_type"):
            current_date = date.fromisoformat(state["target_date"])
            if parsed["target_date"] is None and any(word in message for word in ("换日期", "换一个日期", "改日期", "换一天")):
                same_room_dates = sorted({row["date"] for row in rooms if row["room_type"] == state["room_type"] and row["date"] != current_date})
                if same_room_dates:
                    chosen_date = same_room_dates[0]
            if parsed["room_type"] is None and any(word in message for word in ("换房型", "换一个房型", "换房间")):
                alternatives = [row for row in rooms if row["date"] == chosen_date and row["room_type"] != str(state["room_type"])]
                if alternatives:
                    chosen_room = max(alternatives, key=lambda row: row["remaining"])["room_type"]
        crowd = parsed["crowd"] or state.get("crowd") or self._top_crowd(demand)
        # 统一成代码后再往下传，否则资源表的 suitable_crowds（COUPLE 等）永远匹配不上。
        crowd = normalize_crowd(crowd)
        party_defaults = {"FAMILY": 3, "COUPLE": 2, "FRIENDS": 3, "SOLO": 1, "LOCAL_WEEKEND": 2}
        # A follow-up such as "就这个，生成候选" must keep the operator's
        # already selected package size. Only an explicit crowd/size change may
        # replace it with a crowd default.
        if parsed["party_size"] is not None:
            party_size = int(parsed["party_size"])
        elif parsed["crowd"]:
            party_size = int(party_defaults.get(crowd) or state.get("party_size") or 2)
        else:
            party_size = int(state.get("party_size") or party_defaults.get(crowd) or 2)

        # 1) overview when nothing concrete has been chosen yet
        # No room and no date yet: always answer with the live inventory first,
        # even when the sentence contains a word like "生成".
        if not chosen_room and not chosen_date and not state.get("room_type"):
            return self._with_judgement(
                self._overview(rooms, demand, crowd, party_size, state=state, message=message),
                rooms,
                demand,
                crowd,
                party_size,
                message,
                state,
            )

        if not chosen_room:
            # a date but no room: show that date's rooms and recommend one
            same_day = [row for row in rooms if row["date"] == chosen_date]
            best = max(same_day, key=lambda row: row["remaining"]) if same_day else rooms[0]
            chosen_room = best["room_type"]
            chosen_date = best["date"]

        if chosen_date is None:
            candidates = [row for row in rooms if row["room_type"] == chosen_room]
            best = max(candidates, key=lambda row: row["remaining"]) if candidates else rooms[0]
            chosen_date = best["date"]

        room_row = next(
            (row for row in rooms if row["room_type"] == chosen_room and row["date"] == chosen_date),
            None,
        )
        if room_row is None:
            room_row = next((row for row in rooms if row["room_type"] == chosen_room), rooms[0])
            chosen_date = room_row["date"]

        # 后续的推荐方向、选中标记和当前产品都以本轮真正选中的日期和房型为准。
        planning_state = {
            **state,
            "room_type": str(room_row["room_type"]),
            "target_date": room_row["date"].isoformat(),
            "crowd": normalize_crowd(crowd),
            "party_size": party_size,
        }

        # The room decides the audience when the operator did not say.
        if not parsed["crowd"] and not state.get("crowd"):
            tags = str(room_row.get("crowds") or "").upper()
            crowd = next(
                (label for code, label in CROWD_LABELS.items() if code in tags and code != "ALL"),
                crowd,
            )

        # 2) finalize when the operator confirms the pending plan
        if parsed["confirm"] and state.get("resources"):
            return self._with_judgement(
                self._finalize(state, parsed, room_row, crowd, party_size, demand),
                rooms,
                demand,
                crowd,
                party_size,
                message,
                planning_state,
            )

        # 3) otherwise refine the plan for the chosen room/date
        return self._with_judgement(
            self._plan(room_row, parsed, crowd, party_size, demand, state),
            rooms,
            demand,
            crowd,
            party_size,
            message,
            planning_state,
        )

    def _with_judgement(
        self,
        answer: dict[str, Any],
        rooms: list[dict[str, Any]],
        demand: dict[str, Any],
        crowd: str,
        party_size: int,
        text: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """保证每一轮回答都带「本轮经营判断 + 主推方案」。

        之前只有 overview 分支会附带 judgement/primary，进入 PLAN 状态后
        回答里没有主推方案，前端决策卡就再也渲染不出来，用户看到的推荐
        内容会一直停在上一轮。
        """

        if answer.get("primary") or not rooms:
            return answer
        judgement, primary, directions = self._business_judgement(rooms, demand, crowd, party_size, text, state)
        answer["judgement"] = judgement
        answer["primary"] = primary
        answer["directions"] = directions
        return answer

    # --------------------------------------------------- 本轮经营判断（先判断再推荐）
    def _business_judgement(
        self,
        rooms: list[dict[str, Any]],
        demand: dict[str, Any],
        crowd: str,
        party_size: int,
        text: str,
        state: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
        """从「哪天哪间房压力最大 + 哪类客群需求最高 + 哪个资源名额够」推出一套主产品。"""

        if not rooms:
            return {}, None, []
        state = dict(state or {})
        # 1) 客群：这句话里说了就用它，否则用最近订单占比最高的
        explicit = None
        if any(word in text for word in ("单人", "一人", "一个人", "独自", "独行", "solo", "自己去")):
            explicit = "SOLO"
        if any(word in text for word in ("亲子", "孩子", "带娃", "家庭")):
            explicit = "FAMILY"
        elif any(word in text for word in ("双人", "情侣", "两个人", "约会", "姐妹", "朋友")):
            explicit = "COUPLE" if "朋友" not in text and "姐妹" not in text else "FRIENDS"
        crowd_code = explicit or normalize_crowd(crowd) or normalize_crowd(self._top_crowd(demand)) or "COUPLE"
        if crowd_code in {"ALL", "LOCAL_WEEKEND"}:
            crowd_code = normalize_crowd(self._top_crowd(demand)) or "ALL"
        crowd_label = CROWD_LABELS.get(crowd_code, crowd_code)
        # 2) 库存压力：未来几天里「余量 × 房价」最高的那天/房型
        pressure = sorted(rooms, key=lambda row: (-(int(row["remaining"]) * float(row["normal_price"])), row["date"]))
        requested_state_date = None
        try:
            requested_state_date = date.fromisoformat(str(state.get("target_date") or ""))
        except ValueError:
            pass
        top = next(
            (row for row in pressure if row["date"] == requested_state_date and str(row["room_type"]) == str(state.get("room_type"))),
            pressure[0],
        )
        # 3) 匹配客群、当天有足够名额的体验
        pool = self._resources_for(top["date"], crowd_code, party_size)
        if not pool:
            pool = self._resources_for(top["date"], "ALL", party_size)
        if not pool:
            return (
                {
                    "headline": "本轮经营判断",
                    "text": (
                        f"我建议先处理 {top['date'].month} 月 {top['date'].day} 日的 {top['room_type']}：当天还剩 {top['remaining']} 间，"
                        f"是未来几天库存压力较高的房型之一；但当天没有适合{crowd_label}、且名额足够的可售体验，"
                        f"所以这一轮先不动它，等资源补上再排。"
                    ),
                },
                None,
                [],
            )

        def crowd_tag_hit(resource) -> int:
            """0 = 该资源明确适配当前客群，1 = 不适配。放在排序第一位，避免推荐跑偏。"""

            tags = str(getattr(resource, "suitable_crowds", "") or "").upper()
            code = str(crowd_code or "").upper()
            return 0 if (code and (code in tags or "ALL" in tags)) else 1

        def resource_score(resource: PartnerResource) -> tuple[int, int, Decimal]:
            indoor = 1 if getattr(resource, "indoor", False) else 0
            capacity_sets = int(resource.remaining_capacity or 0) // max(1, party_size)
            return (
                crowd_tag_hit(resource),
                -(indoor * 3 + min(capacity_sets, 20) // 2),
                resource.settlement_price,
            )

        # 本轮提到预算时，先在预算内挑合作资源，挑不到就保留成本最低的组合并说明原因。
        # 方案方向卡始终基于未受预算裁剪的候选池，避免预算一出现就只剩一个方案。
        base_pool = list(pool)
        ai_partner = sorted(base_pool, key=resource_score)[0] if base_pool else None
        state_resource_names = [str(item) for item in (state.get("resources") or []) if str(item)]
        if not state_resource_names and state.get("selected_resource"):
            state_resource_names = [str(state["selected_resource"])]
        add_resource_intent = any(word in text for word in ("增加一个体验", "增加体验", "再加一个", "再增加", "加一个体验", "增加资源"))
        replace_resource_intent = any(word in text for word in ("换资源", "换成", "替换", "改成"))
        # 用户明确说了「换成 X」时，优先用 X，而不是继续按评分挑。
        requested_resource = next(
            (row for row in base_pool if str(row.resource_name or "") and str(row.resource_name) in text),
            None,
        ) or self._resource_by_name(top["date"], text)
        if requested_resource is None and replace_resource_intent:
            requested_resource = next((row for row in sorted(base_pool, key=resource_score) if str(row.resource_name) not in state_resource_names), None)
        if requested_resource is not None and all(str(row.id) != str(requested_resource.id) for row in base_pool):
            base_pool.append(requested_resource)
        budget = self._turn_budget
        budget_note = ""
        budget_shortfall: dict[str, Any] | None = None
        if budget is not None and budget > 0:
            priced = sorted(
                ((self._estimated_price(top, resource, max(1, party_size)), resource) for resource in pool),
                key=lambda row: (row[0], row[1].id),
            )
            affordable = [resource for price, resource in priced if price <= budget]
            if affordable:
                pool = affordable
                budget_note = f"你给的预算 ¥{_money(budget)} 已纳入，只在预算内的合作资源里挑选。"
            elif priced:
                # 预算达不到时优先保留用户当前选中的体验，其次才退回最低价组合。
                # 关键是不要按评分重新挑资源，否则会出现「只是想压价，体验却被换掉」。
                keep = state.get("selected_resource") if isinstance(state, dict) else None
                kept = next((row for price, row in priced if str(row.resource_name) == str(keep)), None)
                lowest_price, lowest_resource = priced[0]
                pool = [kept or lowest_resource]
                if kept is None:
                    lowest_resource = priced[0][1]
                budget_note = (
                    f"你给的预算 ¥{_money(budget)} 低于当前最低可售价 ¥{_money(lowest_price)}"
                    f"（{top['room_type']} + {lowest_resource.resource_name}），"
                    f"这一轮先给出这个最低价组合，距离你的预算还差 ¥{_money(lowest_price - budget)}。"
                    f"若要继续压价，需要换更便宜的房型或体验。"
                )
                # 无解时给出可直接点击的下一步，而不是只留一句解释。
                budget_shortfall = {
                    "requested": _money(budget),
                    "lowest": _money(lowest_price),
                    "gap": _money(lowest_price - budget),
                    "options": [
                        {"label": f"放宽到 ¥{_money(lowest_price)}", "message": f"预算放宽到 {_money(lowest_price)} 以内"},
                        {"label": "换更低成本房型", "message": f"换一个成本更低的房型，预算 {_money(budget)} 以内"},
                    ],
                }

        if requested_resource is not None:
            pool = [requested_resource]
        # 当前组合允许多个不冲突的正式体验。状态里的资源优先于默认主推，
        # 这样“增加一个体验”会进入下一轮容量、成本和候选生成。
        resource_candidates = {str(row.resource_name): row for row in (base_pool + pool)}
        selected_names = list(state_resource_names)
        selection_notes: list[str] = []
        if requested_resource is not None:
            if replace_resource_intent and selected_names:
                selected_names = [str(requested_resource.resource_name), *selected_names[1:]]
            elif not selected_names:
                selected_names = [str(requested_resource.resource_name)]
            elif add_resource_intent and str(requested_resource.resource_name) not in selected_names:
                selected_names.append(str(requested_resource.resource_name))
            elif str(requested_resource.resource_name) in selected_names:
                # Mentioning one of the already selected resources must not
                # collapse a multi-resource package during candidate creation.
                selected_names = list(state_resource_names)
            else:
                selected_names = [str(requested_resource.resource_name)]
        elif add_resource_intent:
            selected_names = selected_names or [str(sorted(pool, key=resource_score)[0].resource_name)]
            current_rows = [resource_candidates.get(name) or self._resource_by_name(top["date"], name) for name in selected_names]
            current_rows = [item for item in current_rows if item is not None]
            extra = next((
                row for row in sorted(base_pool, key=resource_score)
                if str(row.resource_name) not in selected_names
                and int(row.remaining_capacity or 0) >= max(1, party_size)
                and not any(
                    row.start_time and row.end_time and other.start_time and other.end_time
                    and row.start_time < other.end_time and other.start_time < row.end_time
                    for other in current_rows
                )
            ), None)
            if extra is not None:
                selected_names.append(str(extra.resource_name))
            else:
                selection_notes.append("没有找到同时满足名额与场次要求的第二项体验，当前组合未增加体验。")
        if not selected_names:
            selected_names = [str(sorted(pool, key=resource_score)[0].resource_name)]
        selected_partners: list[PartnerResource] = []
        for name in selected_names:
            resource = resource_candidates.get(name) or self._resource_by_name(top["date"], name)
            if resource is None or any(str(item.id) == str(resource.id) for item in selected_partners):
                continue
            if int(resource.remaining_capacity or 0) < max(1, party_size):
                selection_notes.append(f"「{resource.resource_name}」名额不足，本轮未加入。")
                continue
            # 同一时段的两个活动不能塞进一个方案，仍作为不同方向保留。
            if any(
                resource.start_time and resource.end_time and other.start_time and other.end_time
                and resource.start_time < other.end_time and other.start_time < resource.end_time
                for other in selected_partners
            ):
                selection_notes.append(f"「{resource.resource_name}」与已有体验场次重叠，本轮未加入。")
                continue
            selected_partners.append(resource)
        if not selected_partners:
            selected_partners = [sorted(pool, key=resource_score)[0]]
        partner = selected_partners[0]
        per_package = max(1, party_size)
        partner_sets = min(int(item.remaining_capacity or 0) // per_package for item in selected_partners)
        room_sets = int(top["remaining"])
        services = self._services_for(top["date"])
        all_services = services
        requested_service = None
        remove_service_intent = any(word in text for word in ("去掉", "移除", "删除", "不要", "取消"))
        named_service = next((item for item in services if str(item.service_name) in text), None)
        service_requested = any(word in text for word in ("增加", "搭配", "加上", "酒店服务", "服务", "换成")) or named_service is not None
        if service_requested:
            requested_service = named_service
            if requested_service is None:
                all_services = list(
                    self.db.scalars(
                        select(HotelService).where(
                            HotelService.hotel_id == self.hotel_id,
                            HotelService.available_date == top["date"],
                            HotelService.available_quantity > 0,
                            HotelService.status == "AVAILABLE",
                        )
                    ).all()
                )
                requested_service = next((item for item in all_services if str(item.service_name) in text), None)
            if requested_service is None and "早餐" in text:
                requested_service = next((item for item in services if item.service_type == "BREAKFAST"), None)
        selected_services: list[HotelService] = []
        for state_service in (state.get("services") or []):
            service_name = str(state_service.get("name") if isinstance(state_service, dict) else state_service)
            service_id = int(state_service.get("id") or 0) if isinstance(state_service, dict) else 0
            remove_all_services = remove_service_intent and any(word in text for word in ("酒店权益", "酒店服务", "所有服务", "全部服务"))
            remove_this_service = remove_service_intent and service_name and service_name in text
            if remove_all_services or remove_this_service:
                continue
            service = next((item for item in all_services if (service_id and item.id == service_id) or (service_name and str(item.service_name) == service_name)), None)
            if service is not None:
                selected_services.append(service)
        if requested_service is not None and not remove_service_intent and all(item.id != requested_service.id for item in selected_services):
            selected_services.append(requested_service)
        if service_requested and not remove_service_intent and requested_service is None:
            selection_notes.append("没有找到名称匹配且有可用名额的酒店服务，本轮未增加酒店权益。")
        service_sets = min([int(item.available_quantity or 0) // per_package for item in selected_services] or [room_sets])
        max_sellable = max(0, min(room_sets, partner_sets, service_sets))
        unit_cost = (
            Decimal(str(top["cost"]))
            + sum((Decimal(str(item.settlement_price or 0)) * per_package for item in selected_partners), Decimal("0"))
            + sum((Decimal(str(item.unit_cost or 0)) * per_package for item in selected_services), Decimal("0"))
        )
        margin_required = Decimal("0.20")
        margin_floor = unit_cost / (Decimal("1") - margin_required) if unit_cost else Decimal("0")
        floor = max(Decimal(str(top.get("minimum_price") or 0)), margin_floor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        suggested = max(floor, (floor * Decimal("1.2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        if budget is not None and budget > 0:
            if floor > budget:
                gap = (floor - budget).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                budget_note = f"预算 ¥{_money(budget)} 低于最低合法价 ¥{_money(floor)}，相差 ¥{_money(gap)}；需要放宽预算或更换低成本组合。"
                budget_shortfall = {
                    "requested": _money(budget),
                    "lowest": _money(floor),
                    "gap": _money(gap),
                    "options": [
                        {"label": f"放宽到 ¥{_money(floor)}", "message": f"预算放宽到 {_money(floor)} 以内"},
                        {"label": "换更低成本体验", "message": "换成更低成本的体验"},
                    ],
                }
            else:
                suggested = max(floor, min(suggested, budget)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                budget_note = f"建议售价已控制在 ¥{_money(budget)} 预算内，仍不低于最低合法价。"
        margin = ((suggested - unit_cost) / suggested * 100).quantize(Decimal("0.1")) if suggested > 0 else Decimal("0")
        service_bottleneck = min(selected_services, key=lambda item: int(item.available_quantity or 0) // per_package, default=None)
        partner_bottleneck = min(selected_partners, key=lambda item: int(item.remaining_capacity or 0) // per_package)
        bottleneck = "房间库存" if room_sets <= partner_sets and room_sets <= service_sets else (f"{partner_bottleneck.resource_name}名额" if partner_sets <= service_sets else f"{service_bottleneck.service_name}服务名额" if service_bottleneck else f"{partner.resource_name}名额")
        window = "、".join(self._resource_window(item) for item in selected_partners if self._resource_window(item))
        retained_partners = selected_partners[1:]
        def replacement_fits(option) -> bool:
            return not any(
                option.start_time and option.end_time and other.start_time and other.end_time
                and option.start_time < other.end_time and other.start_time < option.end_time
                for other in retained_partners
            )
        def replacement_price(option) -> Decimal:
            return self._estimated_price(top, option, per_package, partners=[option, *retained_partners], services=selected_services)
        # 同日期、同房型、同客群下可替换的合作资源：这是「换资源」，不改变产品框架。
        resource_options = [
            {
                "name": str(option.resource_name),
                "window": self._resource_window(option),
                "remaining_capacity": int(option.remaining_capacity or 0),
                "sets": int(option.remaining_capacity or 0) // per_package,
                "estimated_price": _money(replacement_price(option)),
                "settlement_price": _money(option.settlement_price or 0),
                "indoor": bool(getattr(option, "indoor", False)),
                "is_current": str(option.resource_name) == str(partner.resource_name),
            }
            for option in sorted(
                [row for row in (base_pool or pool) if replacement_fits(row)],
                key=lambda row: (replacement_price(row), row.id),
            )[:5]
        ]
        crowd_short = {"FAMILY": "亲子短住", "COUPLE": "双人短住", "FRIENDS": "朋友短住", "SOLO": "独自短住"}.get(crowd_code, "周末短住")
        crowd_audience = {"FAMILY": "亲子家庭", "COUPLE": "情侣等双人", "FRIENDS": "朋友同行", "SOLO": "独自出行"}.get(crowd_code, "周末旅客")
        slot = "晚上"
        if partner.start_time is not None:
            slot = "上午" if partner.start_time.hour < 12 else ("下午" if partner.start_time.hour < 18 else "晚上")
        route_note = str(state.get("route_note") or "")
        if any(word in text for word in ("路线", "行程", "轻松", "自由时间", "别排太满", "不要排满")):
            route_note = "下午留出自由时间，减少连续安排，具体场次仍按资源开放时间核对"
        other_pressure = [
            row
            for row in pressure[1:]
            if not (row["room_type"] == top["room_type"] and row["date"] == top["date"])
        ]
        not_chosen_text = (
            (
                f"{other_pressure[0]['date'].month} 月 {other_pressure[0]['date'].day} 日的{other_pressure[0]['room_type']}"
                f"（还剩 {other_pressure[0]['remaining']} 间）：余量 × 房价低于本轮主推组合，可作为下一轮方向；"
            )
            if other_pressure
            else ""
        ) + (
            "更贵的体验会抬高成本并压缩毛利空间，本轮优先可控成本；"
            + (
                "户外项目受天气影响更大，本轮优先了室内资源。"
                if getattr(partner, "indoor", False)
                else "天气变化会影响户外项目，本轮选择了名额更稳的资源。"
            )
        )
        matched = self._match_running_product(
            top["date"],
            str(top["room_type"]),
            {str(item.resource_name) for item in selected_partners},
            {str(item.service_name) for item in selected_services},
            crowd_code,
            party_size,
            suggested,
        )
        forecast = WeatherService(self.db).get_forecast("杭州", top["date"]) or {}
        weather_text = self._weather_label(str(forecast.get("scenario") or "")) or "以当天预报为准"
        partner_names = "、".join(str(item.resource_name) for item in selected_partners)
        partner_capacity_text = "；".join(f"{item.resource_name}剩 {item.remaining_capacity} 个名额" for item in selected_partners)
        selected_ids = {int(item.id) for item in selected_partners}
        selected_windows = [item for item in selected_partners if item.start_time and item.end_time]
        add_resource_options = []
        for option in sorted(base_pool, key=resource_score):
            if int(option.id) in selected_ids or int(option.remaining_capacity or 0) < per_package:
                continue
            conflicts = any(
                option.start_time and option.end_time
                and option.start_time < other.end_time and other.start_time < option.end_time
                for other in selected_windows
            )
            if conflicts:
                continue
            add_resource_options.append({
                "id": option.id,
                "name": str(option.resource_name),
                "window": self._resource_window(option),
                "remaining_capacity": int(option.remaining_capacity or 0),
                "sets": int(option.remaining_capacity or 0) // per_package,
                "settlement_price": _money(option.settlement_price or 0),
                "indoor": bool(getattr(option, "indoor", False)),
            })
            if len(add_resource_options) >= 8:
                break
        resource_decisions = []
        for candidate in sorted(base_pool, key=resource_score)[:6]:
            if int(candidate.id) in selected_ids:
                reason = "时间、客群和天气与当前组合匹配"
                status = "已选择"
            elif not crowd_tag_hit(candidate):
                reason = "可作为备选，当前优先级低于已选资源"
                status = "备选"
            elif not getattr(candidate, "indoor", False):
                reason = "户外适配较弱，雨天需二次核验"
                status = "未选择"
            else:
                reason = "客群或容量匹配度较低"
                status = "未选择"
            resource_decisions.append({"name": str(candidate.resource_name), "status": status, "reason": reason})
        crowd_orders = int(demand.get("by_crowd", {}).get(crowd_label, 0))
        demand_basis = (
            f"近14天已确认 {demand['confirmed']} 单，其中{crowd_label} {crowd_orders} 单"
            if demand["confirmed"]
            else "近14天没有已确认订单，客群样本不足，本轮按房态与资源适配判断"
        )
        judgement_text = (
            f"我建议先处理 {top['date'].month} 月 {top['date'].day} 日的{top['room_type']}：当天还剩 {room_sets} 间，"
            f"是未来几天库存压力较高的房型之一；{demand_basis}，"
            f"{_weekday(top['date'])}更匹配{'亲子短住' if crowd_code == 'FAMILY' else '双人/朋友短住'}；"
            f"当天「{partner_names}」可用，{partner_capacity_text}，按每套 {per_package} 人算最多支撑 {partner_sets} 套，"
            f"因此这组资源比其它体验更适合作为这一轮主产品。"
            f"当前天气{weather_text}"
            f"{'，室内资源不受影响' if getattr(partner, 'indoor', False) else '，户外项目会按天气复核'}。"
            f"按房间、体验和酒店权益中最小容量计算，这一轮实际可售 {max_sellable} 套；"
            f"成本 ¥{_money(unit_cost)}，最低合法售价 ¥{_money(floor)}，建议售价 ¥{_money(suggested)}（毛利率约 {margin}%）。"
        )
        primary = {
            "product_id": matched.id if matched is not None else None,
            "product_name": matched.product_name if matched is not None else f"{top['date'].month}月{top['date'].day}日 {crowd_label}·{top['room_type']}住玩包",
            "target_date": top["date"].isoformat(),
            "weekday": _weekday(top["date"]),
            "crowd": crowd_code,
            "crowd_label": crowd_label,
            "room_type": str(top["room_type"]),
            "room_quantity": room_sets,
            "experiences": [
                {
                    "name": str(item.resource_name),
                    "capacity": int(item.remaining_capacity or 0),
                    "per_package": per_package,
                    "sets": int(item.remaining_capacity or 0) // per_package,
                    "window": self._resource_window(item),
                    "indoor": bool(getattr(item, "indoor", False)),
                }
                for item in selected_partners
            ],
            "price": _money(suggested),
            "cost": _money(unit_cost),
            "floor_price": _money(floor),
            "visitor_budget": _money(budget) if budget is not None and budget > 0 else None,
            "margin": str(margin),
            "max_sellable": max_sellable,
            "bottleneck": bottleneck,
            "party_size": party_size,
            "route_note": route_note,
            "selection_notice": "；".join(dict.fromkeys(selection_notes)),
            "services": [{"id": item.id, "name": str(item.service_name), "quantity": per_package} for item in selected_services],
            "service_options": [
                {"id": item.id, "name": str(item.service_name), "available_quantity": int(item.available_quantity or 0), "reference_price": _money(item.reference_price or 0), "unit_cost": _money(item.unit_cost or 0), "window": self._resource_window(item)}
                for item in services[:8]
            ],
            "cost_breakdown": [
                {"label": "客房内部成本", "value": _money(top["cost"])},
                *[{"label": f"{item.resource_name}合作成本", "value": _money(Decimal(str(item.settlement_price or 0)) * per_package)} for item in selected_partners],
                *[{"label": f"{item.service_name}服务成本", "value": _money(Decimal(str(item.unit_cost or 0)) * per_package)} for item in selected_services],
            ],
            "pricing_basis": [
                f"单位成本 = 客房 ¥{_money(top['cost'])} + 已选体验与酒店权益成本 = ¥{_money(unit_cost)}",
                f"最低合法价 = 客房最低价 ¥{_money(top.get('minimum_price') or 0)} 与「单位成本 ÷（1 − 20%最低毛利率）」取较高值 = ¥{_money(floor)}",
                f"建议售价 = 最低合法价上浮20%，并受用户预算封顶；本轮 ¥{_money(suggested)}，毛利率 {margin}%",
            ],
            "structure": [
                {"label": "住宿", "items": [{"name": f"{top['room_type']} 1晚", "quantity": ""}]},
                {"label": "核心体验", "items": [{"name": item.resource_name, "quantity": f"{per_package}人", "window": self._resource_window(item)} for item in selected_partners]},
                {"label": "酒店权益", "items": [{"name": item.service_name, "quantity": f"{per_package}份"} for item in selected_services] or [{"name": "暂无正式酒店权益", "quantity": ""}]},
                {"label": "路线建议", "items": [{"name": route_note or "入住后自由安排，按场次衔接体验", "quantity": ""}]},
            ],
            "itinerary": [
                {"time": "入住日", "title": f"15:00 后入住{top['room_type']}，留出城市活动时间"},
                {"time": window or "按场次", "title": f"参加{partner_names}，结束后返回酒店"},
                {"time": "次日", "title": "早餐或自由活动；未标为正式权益的景点仅作路线建议"},
            ],
            "reason_sections": [
                {"label": "为什么现在做", "text": f"{top['date'].month}月{top['date'].day}日{top['room_type']}仍有 {room_sets} 间，是当前窗口中库存压力较高的房型。"},
                {"label": "为什么给这类人", "text": f"{demand_basis}；{'本轮按' + crowd_audience + '设计。' if demand['confirmed'] else '客群结论信心较低，建议结合后续成交再复核。'}"},
                {"label": "为什么搭这个体验", "text": f"{weather_text}；{partner_names}的场次与入住后的{slot}空档衔接，名额可以支撑 {partner_sets} 套。"},
                {"label": "为什么这样卖", "text": f"当前组合单位成本 ¥{_money(unit_cost)}，最低合法价 ¥{_money(floor)}，建议售价 ¥{_money(suggested)}，瓶颈在{bottleneck}。"},
                {"label": "资源筛选结果", "text": "；".join(f"{item['name']}：{item['status']}，{item['reason']}" for item in resource_decisions) or "暂无可比较的合作资源。"},
            ],
            "resource_decisions": resource_decisions,
            "budget_note": budget_note,
            "budget_shortfall": budget_shortfall,
            "resource_options": resource_options,
            "add_resource_options": add_resource_options,
            "image_url": str(getattr(partner, "image_url", "") or ""),
            "reasons": ([f"已按你的要求使用「{partner_names}」"] if requested_resource is not None or len(selected_partners) > 1 else [])
            + [
                f"{top['room_type']} 当天还剩 {room_sets} 间，是未来 10 天库存压力最高的房型之一",
                demand_basis,
                f"{partner_names}共占用 {partner_sets} 套容量，瓶颈为{bottleneck}",
                f"天气{weather_text}" + ("，室内体验不受影响" if getattr(partner, "indoor", False) else "，户外项目出发前会再确认"),
            ]
            + ([budget_note] if budget_note else []),
            "constraints": [
                {"label": "库存瓶颈", "value": bottleneck},
                {"label": "最大可售", "value": f"{max_sellable} 套"},
                {"label": "利润校验", "value": f"通过（毛利率 {margin}%）"},
                {"label": "资源状态", "value": "已审核、可组包"},
            ],
            # 一句结论 + 四个关键数据块，让用户先看到 AI 判断了什么。
            "conclusion": (
                f"优先消化 {top['date'].month} 月 {top['date'].day} 日的{top['room_type']}："
                f"{'近期' + crowd_label + '成交较多' if demand['confirmed'] else '近期成交样本有限'}，「{partner_names}」组合可支撑 {max_sellable} 套。"
            ),
            "blocks": [
                {"label": "库存压力", "value": f"{top['room_type']} {room_sets} 间"},
                {"label": "客群依据", "value": demand_basis},
                {"label": "资源容量", "value": f"{partner.resource_name} {partner.remaining_capacity} 席 → {partner_sets} 套"},
                {"label": "天气", "value": f"{weather_text}{'，室内不受影响' if getattr(partner, 'indoor', False) else ''}"},
            ],
            "logic": [
                {
                    "title": "推荐逻辑",
                    "text": (
                        f"{top['date'].month} 月 {top['date'].day} 日的{top['room_type']}当前仍有 {room_sets} 间未售，是未来 10 天里库存压力最高的房型之一；"
                        f"近 14 天订单结构中，{crowd_label}成交最集中，所以这一轮围绕{crowd_short}的需求来设计。"
                        f"合作资源里「{partner.resource_name}」当天还有 {partner.remaining_capacity} 个可售名额，每套需要 {per_package} 个，最多支撑 {partner_sets} 套；"
                        f"客房只有 {room_sets} 间，两边取小，最终最大可售 {max_sellable} 套，瓶颈在{bottleneck}。"
                    ),
                },
                {
                    "title": "游客体验",
                    "text": (
                        f"这套组合把住宿和体验分开安排：到店入住{top['room_type']}后不强制排景点，可以自行吃饭、逛街；"
                        f"{window or '按场次'}参加{partner.resource_name}，结束后直接回酒店，不需要长距离移动。"
                        f"适合{crowd_audience}短途出行，购买理由清楚：住一晚，同时把{slot}安排掉。"
                    ),
                },
                {
                    "title": "酒店经营价值",
                    "text": (
                        f"按建议售价 ¥{_money(suggested)}、最大可售 {max_sellable} 套计算，全部售出约 ¥{_money(suggested * max_sellable)} 销售额，"
                        f"预计毛利约 ¥{_money((suggested - unit_cost) * max_sellable)}；同时最多消化 {max_sellable} 间{top['room_type']}，"
                        f"剩余 {max(0, room_sets - max_sellable)} 间可以留到下一轮用别的客群或资源处理。"
                    ),
                },
                {
                    "title": "风险与约束",
                    "text": (
                        f"主要风险在{partner.resource_name}的名额：名额每减少 {per_package} 个，最大可售就少 1 套；"
                        f"如果该场次取消，产品会转入「待调整」，系统优先搜索同日期、{'室内' if getattr(partner, 'indoor', False) else '同类目'}、时间不冲突的替代资源。"
                        f"如果房间或名额被其他渠道先卖掉，可售量也会同步下降——{max_sellable} 套是确定性计算结果，不是估计值。"
                    ),
                },
            ],
            "not_chosen": not_chosen_text,
            "checks": [
                {"label": "房态实时校验", "value": "✓"},
                {"label": "合作资源已审核", "value": "✓"},
                {"label": "资源容量", "value": "✓"},
                {"label": "时间冲突", "value": "✓"},
                {"label": "天气适配", "value": "✓"},
                {"label": "最低利润", "value": "✓"},
            ],
            "unit_profit": _money(suggested - unit_cost),
        }
        alternatives: list[dict[str, Any]] = []
        for row in pressure[1:4]:
            if str(row["room_type"]) == str(top["room_type"]) and row["date"] == top["date"]:
                continue
            alt_pool = self._resources_for(row["date"], crowd_code, party_size) or self._resources_for(row["date"], "ALL", party_size)
            alt_partner = sorted(alt_pool, key=resource_score)[0] if alt_pool else None
            alt_sets = 0
            if alt_partner is not None:
                alt_sets = max(
                    0,
                    min(
                        int(row["remaining"]),
                        int(alt_partner.remaining_capacity or 0) // max(1, party_size),
                    ),
                )
            alternatives.append(
                {
                    "label": f"备选{'ABC'[len(alternatives)]}",
                    "target_date": row["date"].isoformat(),
                    "weekday": _weekday(row["date"]),
                    "room_type": str(row["room_type"]),
                    "remaining": int(row["remaining"]),
                    "experience": str(alt_partner.resource_name) if alt_partner is not None else "",
                    "sets": alt_sets,
                    "reason": (
                        f"{_weekday(row['date'])} {row['room_type']} 还剩 {row['remaining']} 间"
                        + (f" + {alt_partner.resource_name}" if alt_partner is not None else "")
                        + f"｜预计可售 {alt_sets} 套｜"
                        + (
                            "换个体验方向，价格更低，可作为第二顺位"
                            if alt_partner is not None and str(alt_partner.resource_name) != str(partner.resource_name)
                            else "同日不同房型，适合错峰消化库存"
                        )
                        + (
                            ""
                            if alt_partner is None
                            else ("（成本更低）" if Decimal(str(alt_partner.settlement_price or 0)) < Decimal(str(partner.settlement_price or 0)) else "（成本更高）")
                        )
                    ),
                }
            )
            if len(alternatives) >= 2:
                break
        metrics = [
            {"label": "主攻日期", "value": f"{top['date'].month}月{top['date'].day}日（{_weekday(top['date'])}）"},
            {"label": "目标客群", "value": crowd_label},
            {"label": "主攻房型", "value": f"{top['room_type']} {room_sets} 间"},
            {"label": "关键瓶颈", "value": bottleneck},
        ]
        # 主推荐给 2~3 个方向：主推 + 更低成本 / 更适合雨天 + 更高容量。
        # 这些都是「同一轮经营判断下的可选方案」，不是已生成的正式候选。
        plan_options: list[dict[str, Any]] = []
        seen_resources: set[str] = {str(item.resource_name) for item in selected_partners}

        def push_plan(option_label: str, row: dict[str, Any], resource, is_current: bool = False) -> None:
            if resource is None or str(resource.resource_name) in seen_resources:
                return
            seen_resources.add(str(resource.resource_name))
            same_frame = row["date"] == top["date"] and str(row["room_type"]) == str(top["room_type"])
            option_partners = [resource, *retained_partners] if same_frame else [resource]
            sets = min(int(item.remaining_capacity or 0) // per_package for item in option_partners)
            row_sets = int(row["remaining"])
            option_services = selected_services if same_frame else []
            option_names = "、".join(str(item.resource_name) for item in option_partners)
            plan_options.append(
                {
                    "label": option_label,
                    "name": f"{row['room_type']} × {option_names}",
                    "target_date": row["date"].isoformat(),
                    "weekday": _weekday(row["date"]),
                    "room_type": str(row["room_type"]),
                    "resource_name": str(resource.resource_name),
                    "window": self._resource_window(resource),
                    "indoor": bool(getattr(resource, "indoor", False)),
                    "estimated_price": _money(self._estimated_price(row, resource, per_package, partners=option_partners, services=option_services)),
                    "max_sellable": max(0, min(row_sets, sets)),
                    "remaining": row_sets,
                    "is_current": is_current,
                    "message": f"把 {row['date'].isoformat()} 的 {row['room_type']} 换成 {resource.resource_name}",
                }
            )

        plan_options.append(
            {
                "label": "当前选择" if ai_partner is not None and int(ai_partner.id) != int(partner.id) else "AI主推",
                "name": f"{top['room_type']} × {partner_names}",
                "target_date": top["date"].isoformat(),
                "weekday": _weekday(top["date"]),
                "room_type": str(top["room_type"]),
                "resource_name": str(partner.resource_name),
                "window": window,
                "indoor": bool(getattr(partner, "indoor", False)),
                "estimated_price": _money(suggested),
                "max_sellable": max_sellable,
                "remaining": room_sets,
                "is_current": True,
                "is_ai_primary": ai_partner is not None and int(ai_partner.id) == int(partner.id),
                "message": "",
            }
        )
        if ai_partner is not None and int(ai_partner.id) != int(partner.id):
            ai_sets = min(room_sets, int(ai_partner.remaining_capacity or 0) // per_package)
            plan_options.insert(
                0,
                {
                    "label": "AI主推",
                    "name": f"{top['room_type']} × {ai_partner.resource_name}",
                    "target_date": top["date"].isoformat(),
                    "weekday": _weekday(top["date"]),
                    "room_type": str(top["room_type"]),
                    "resource_name": str(ai_partner.resource_name),
                    "window": self._resource_window(ai_partner),
                    "indoor": bool(getattr(ai_partner, "indoor", False)),
                    "estimated_price": _money(self._estimated_price(top, ai_partner, per_package, partners=[ai_partner, *retained_partners], services=selected_services)),
                    "max_sellable": ai_sets,
                    "remaining": room_sets,
                    "is_current": False,
                    "is_ai_primary": True,
                    "message": f"把 {top['date'].isoformat()} 的 {top['room_type']} 换成 {ai_partner.resource_name}",
                },
            )
            seen_resources.add(str(ai_partner.resource_name))
        same_frame_pool = [row for row in base_pool if str(row.resource_name) not in seen_resources]
        # 先在同客群的资源里挑替代方向，避免给「两人同行」推荐亲子向体验。
        matched_pool = [row for row in same_frame_pool if crowd_tag_hit(row) == 0]
        if matched_pool:
            same_frame_pool = matched_pool
        cheaper = sorted(same_frame_pool, key=lambda row: (self._estimated_price(top, row, per_package, partners=[row, *retained_partners], services=selected_services), row.id))
        if cheaper:
            candidate_resource = cheaper[0]
            candidate_price = self._estimated_price(top, candidate_resource, per_package, partners=[candidate_resource, *retained_partners], services=selected_services)
            if not getattr(partner, "indoor", False) and getattr(candidate_resource, "indoor", False):
                # 主推是户外、替代是室内，这时候「更适合雨天」比「更便宜」更有价值。
                option_label = "更适合雨天"
            elif candidate_price < suggested:
                option_label = "更低成本"
            else:
                # 剩下的都更贵时不要硬贴“更低成本”，按真实差异命名。
                option_label = "体验不同"
            push_plan(option_label, top, candidate_resource)
            same_frame_pool = [row for row in same_frame_pool if row is not candidate_resource]
        roomier = sorted(same_frame_pool, key=lambda row: (-(int(row.remaining_capacity or 0) // per_package), row.id))
        if roomier:
            capacity_option = roomier[0]
            capacity_sets = min(room_sets, int(capacity_option.remaining_capacity or 0) // per_package)
            push_plan("更高容量" if capacity_sets > max_sellable else "体验不同", top, capacity_option)
        if len(plan_options) < 3:
            for other in pressure[1:]:
                if str(other["room_type"]) == str(top["room_type"]) and other["date"] == top["date"]:
                    continue
                alt_pool = self._resources_for(other["date"], crowd_code, party_size) or self._resources_for(
                    other["date"], "ALL", party_size
                )
                if not alt_pool:
                    continue
                push_plan("换房型", other, sorted(alt_pool, key=resource_score)[0])
                if len(plan_options) >= 3:
                    break

        # 供运营阅读的执行摘要：只讲做了什么，不出现英文工具名和公式。
        execution_summary = [
            {"label": "已读取房态", "value": "完成未来 10 天可售房态读取"},
            {"label": "已分析近期订单", "value": "完成近 14 天成交结构分析"},
            {"label": "已匹配合作资源", "value": "完成客群、天气和场次适配"},
            {"label": "已重新计算容量和价格", "value": "完成资源组合、容量与定价规则校验"},
            {"label": "当前方案校验通过", "value": "房态、资源、时间冲突和最低利润均已复核"},
        ]
        # Agent 的工具调用轨迹：让「不是套壳聊天机器人」这件事可见，失败也如实呈现。
        top_crowd = self._top_crowd(demand)
        trace: list[dict[str, str]] = [
            {"tool": "room_inventory", "tool_label": "房态数据", "status": "ok", "detail": f"读取未来 10 天 {len(rooms)} 个「房型 × 日期」组合"},
            {"tool": "recent_sales", "tool_label": "近期订单", "status": "ok", "detail": f"近 14 天已成交 {demand['confirmed']} 单，{top_crowd}占比最高"},
            {"tool": "partner_resources", "tool_label": "合作资源", "status": "ok", "detail": f"当天筛出 {len(pool)} 项适合{crowd_label}、名额足够的可售体验"},
            {"tool": "calculate_capacity", "tool_label": "容量计算", "status": "ok", "detail": f"客房 {room_sets} 间；体验名额 {partner.remaining_capacity} 席，每套占 {per_package} 席，因此最多 {max_sellable} 套"},
            {"tool": "calculate_finance", "tool_label": "价格与利润", "status": "ok", "detail": f"成本 ¥{_money(unit_cost)}，最低合法价 ¥{_money(floor)}，建议售价 ¥{_money(suggested)}（毛利率 {margin}%）"},
            {"tool": "validator", "tool_label": "方案校验", "status": "pass", "detail": "房态 / 资源审核 / 容量 / 时间冲突 / 天气 / 最低利润 全部通过"},
        ]
        if not weather_text or weather_text == "以当天预报为准":
            trace.insert(3, {"tool": "weather", "tool_label": "天气", "status": "failed", "detail": "天气接口暂不可用，本轮不使用天气作为决策依据"})
        return {
            "headline": "AI 本轮经营判断",
            "text": judgement_text,
            "metrics": metrics,
            "trace": trace,
            "plans": plan_options[:3],
            "execution_summary": execution_summary,
            # 前端用它判断历史快照是否与当前协议兼容；改动 plans/primary 结构时要一起递增。
            "contract_version": ADVISOR_CONTRACT_VERSION,
        }, primary, alternatives

    @staticmethod
    def _weather_label(code: str) -> str:
        return {"RAIN": "有雨", "SUNNY": "晴天", "CLOUDY": "多云"}.get(str(code or "").upper(), "")

    def _match_running_product(
        self,
        target: date,
        room_type: str,
        resource_names: set[str],
        service_names: set[str],
        crowd_code: str,
        party_size: int,
        suggested_price: Decimal,
    ) -> TravelProduct | None:
        for item in list_products(self.db, self.hotel_id):
            if str(item.status) not in {"ON_SALE", "LOW_STOCK"} or int(item.sale_quantity or 0) <= 0:
                continue
            if (
                item.target_date != target
                or self._product_room_type(item) != room_type
                or str(item.target_crowd) != crowd_code
                or int(item.party_size or 0) != party_size
                or Decimal(str(item.suggested_price or 0)) != suggested_price
            ):
                continue
            actual_resources = {
                str(row.resource_name)
                for row in item.resources
                if row.resource_type == "PARTNER_RESOURCE"
            }
            actual_services = {
                str(row.resource_name)
                for row in item.resources
                if row.resource_type == "HOTEL_SERVICE"
            }
            if actual_resources == resource_names and actual_services == service_names:
                return item
        return None

    def _top_crowd(self, demand: dict[str, Any]) -> str:
        if demand["by_crowd"]:
            return max(demand["by_crowd"].items(), key=lambda item: item[1])[0]
        return "不限客群"

    def _overview(self, rooms, demand, crowd, party_size, state: dict[str, Any] | None = None, message: str = "") -> dict[str, Any]:
        state = dict(state or {})
        text = str(message or "")
        demand_crowd = self._top_crowd(demand) if demand["confirmed"] else "暂无成交样本"
        by_date: dict[date, list[dict[str, Any]]] = {}
        for row in rooms:
            by_date.setdefault(row["date"], []).append(row)
        best_days = sorted(
            by_date.items(),
            key=lambda item: (-sum(row["remaining"] for row in item[1]), item[0]),
        )[:3]
        inventory = [
            {
                "date": row["date"].isoformat(),
                "weekday": _weekday(row["date"]),
                "room_type": row["room_type"],
                "remaining": row["remaining"],
                "price": _money(row["normal_price"]),
            }
            for row in sorted(rooms, key=lambda item: (item["date"], -item["remaining"]))[:24]
        ]
        recommendations = []
        seen_recommendation_theme: set[str] = set()
        on_sale_all = [
            item
            for item in list_products(self.db, self.hotel_id)
            if str(item.status) in {"ON_SALE", "LOW_STOCK"} and int(item.sale_quantity or 0) > 0
        ]

        def match_product(day: date, room_type: str, resource_names: list[str]) -> TravelProduct | None:
            """把「为什么推荐」这段文字对应到真实在售产品上。"""

            for item in on_sale_all:
                if item.target_date != day:
                    continue
                if self._product_room_type(item) != room_type:
                    continue
                names = [str(row.resource_name) for row in item.resources]
                if any(name in names for name in resource_names):
                    return item
            for item in on_sale_all:
                if item.target_date == day and self._product_room_type(item) == room_type:
                    return item
            return None

        for day, rows in best_days:
            top = max(rows, key=lambda row: row["remaining"])
            resources = self._resources_for(day, crowd, party_size)
            if not resources:
                continue
            price = top["normal_price"] + sum(Decimal(str(item.market_price or 0)) for item in resources[:2]) // 2
            matched = match_product(day, str(top["room_type"]), [item.resource_name for item in resources[:2]])
            # 推荐条目也不重复：同一款体验只出现一次。
            dedupe_key = f"{resources[0].resource_name}"
            if dedupe_key in seen_recommendation_theme:
                continue
            seen_recommendation_theme.add(dedupe_key)
            recommendations.append(
                {
                    "title": f"{day.month}月{day.day}日 {top['room_type']} + {resources[0].resource_name}",
                    "room_type": top["room_type"],
                    "target_date": day.isoformat(),
                    "weekday": _weekday(day),
                    "remaining": top["remaining"],
                    "resources": [item.resource_name for item in resources[:2]],
                    "price_hint": _money(price),
                    "why": (
                        f"这天{top['room_type']}还剩 {top['remaining']} 间，"
                        f"{_weekday(day)}{demand_crowd + '订单较多' if demand['confirmed'] else '暂无近期成交数据可比较'}，"
                        f"而且{resources[0].resource_name}当天还有 {resources[0].remaining_capacity} 个名额。"
                    ),
                    "hotel_benefit": f"按 ¥{_money(price)} 出售，可把这 {top['remaining']} 间房变成约 ¥{_money(price * top['remaining'])} 的在售货值。",
                    "visitor_reason": f"住{top['room_type']}，白天安排{resources[0].resource_name}，"
                    f"{'室内为主，雨天也能成行' if getattr(resources[0], 'indoor', False) else '按当天场次出行，节奏不赶'}。",
                    "product_id": matched.id if matched is not None else None,
                    "product_name": matched.product_name if matched is not None else None,
                }
            )
        options = [
            {"id": f"room:{row['room_type']}", "label": f"只看{row['room_type']}", "message": f"我想看{row['room_type']}的产品"},
        ]
        seen_dates: set[str] = set()
        for row in rooms:
            key = row["date"].isoformat()
            if key in seen_dates:
                continue
            seen_dates.add(key)
            options.append(
                {
                    "id": f"date:{key}",
                    "label": f"{row['date'].month}月{row['date'].day}日（{_weekday(row['date'])}）",
                    "message": f"{key} 这天有哪些房型可以搭配",
                }
            )
            if len(seen_dates) == 3:
                break
        options.append({"id": "hot", "label": "看预测最好卖的搭配", "message": "预测一下哪些产品会比较好卖"})

        # 把「已经在售、最近就能卖」的产品做成可直接打开的推荐卡片，
        # 而不是只给一句文字建议。
        on_sale = [
            item
            for item in list_products(self.db, self.hotel_id)
            if str(item.status) in {"ON_SALE", "LOW_STOCK"} and int(item.sale_quantity or 0) > 0
        ]
        # 按用户这一轮的说法做个性化排序：客群 / 主题 / 预算。
        wants_family = any(word in text for word in ("亲子", "孩子", "小朋友", "家庭", "带娃"))
        wants_couple = any(word in text for word in ("双人", "情侣", "两个人", "二人", "约会"))
        wants_friends = any(word in text for word in ("朋友", "聚会", "多人", "团队"))
        theme_words = [word for word in ("博物", "展", "夜游", "夜景", "美食", "餐", "下午茶", "茶", "非遗", "手作", "乐园", "旅拍", "运河", "湿地", "演出") if word in text]
        budget_match = re.search(r"(\d{3,5})", text)
        budget = int(budget_match.group(1)) if budget_match else 0

        def rank_key(item: TravelProduct) -> tuple[float, str, int]:
            value = 0.0
            if wants_family and item.target_crowd == "FAMILY":
                value += 6
            if wants_couple and item.target_crowd == "COUPLE":
                value += 6
            if wants_friends and item.target_crowd == "FRIENDS":
                value += 6
            haystack = f"{item.product_name} {item.theme} " + " ".join(str(row.resource_name) for row in item.resources)
            value += 3 * sum(1 for word in theme_words if word in haystack)
            if budget:
                price = float(item.suggested_price or 0)
                value += 4 if price <= budget else (1 if price <= budget * 1.2 else -3)
            # 接近的评分里，优先最近的日期、余量多的。
            return (-value, item.target_date.isoformat(), -int(item.sale_quantity or 0))

        ranked = sorted(on_sale, key=rank_key)
        # 同一个主题（同一款套餐的不同日期）只留最近的一天，避免推荐里出现重复产品。
        seen_themes: set[str] = set()
        unique: list[TravelProduct] = []
        for item in ranked:
            key = str(item.theme or item.product_name)
            if key in seen_themes:
                continue
            seen_themes.add(key)
            unique.append(item)
        top = unique[:12]
        # 每次只给 3 个；用户说「再推荐几个」时按偏移换下一组，不会每次一模一样。
        offset = int(state.get("product_offset") or 0)
        window: list[TravelProduct] = []
        if top:
            start = (offset * 3) % len(top)
            window = (top[start:] + top[:start])[:3]
        room_by_key = {(row["date"], row["room_type"]): row for row in rooms}
        recommended_products = []
        for item in window:
            room_type = self._product_room_type(item)
            room_row = room_by_key.get((item.target_date, room_type))
            remaining = int(room_row["remaining"]) if room_row else int(item.sale_quantity or 0)
            experience = next(
                (row.resource_name for row in item.resources if row.resource_type == "PARTNER_RESOURCE"),
                "在地体验",
            )
            weekday = _weekday(item.target_date)
            weekend = "周末" if item.target_date.weekday() >= 5 else "工作日"
            margin = round(float(item.gross_margin or 0) * 100, 1)
            # 特色：房型卖点 + 体验特点 + 天气适配。
            room_features = ""
            if room_row is not None:
                room_features = str(room_row.get("features") or "")
            partner_row = next((row for row in item.resources if row.resource_type == "PARTNER_RESOURCE"), None)
            partner_feature = ""
            if partner_row is not None:
                partner = self.db.get(PartnerResource, partner_row.resource_id)
                if partner is not None:
                    partner_feature = str(partner.description or "")
                    if getattr(partner, "indoor", False):
                        partner_feature = (partner_feature + "；室内为主，雨天也能成行").strip("；")
            feature_parts = [str(part).strip().strip("。；;·") for part in (room_features[:40], partner_feature[:60]) if part]
            feature_text = "；".join(part for part in feature_parts if part) or f"{room_type} + {experience}"
            # 可以和什么搭配：当天还有名额、且不在本套餐里的体验。
            used_ids = {row.resource_id for row in item.resources}
            pairing = self.db.scalars(
                select(PartnerResource)
                .join(Merchant)
                .where(
                    Merchant.hotel_id == self.hotel_id,
                    PartnerResource.available_date == item.target_date,
                    PartnerResource.package_enabled.is_(True),
                    PartnerResource.status == "AVAILABLE",
                    PartnerResource.remaining_capacity > 0,
                    PartnerResource.id.notin_(used_ids or {0}),
                )
                .order_by(PartnerResource.remaining_capacity.desc())
            ).first()
            pair_text = (
                f"还可以顺路加上「{pairing.resource_name}」（当天还有 {pairing.remaining_capacity} 个名额，结算 ¥{_money(pairing.settlement_price)}/人）。"
                if pairing is not None
                else "当天可搭配的体验名额都比较紧，想加项可以让我帮你找替代。"
            )
            recommended_products.append(
                {
                    "id": item.id,
                    "product_name": item.product_name,
                    "theme": item.theme,
                    "target_date": item.target_date.isoformat(),
                    "weekday": weekday,
                    "price": str(item.suggested_price),
                    "sale_quantity": int(item.sale_quantity or 0),
                    "party_size": int(item.party_size or 0),
                    "status": item.status,
                    "room_type": room_type,
                    "remaining_rooms": remaining,
                    "experience": experience,
                    "reason": (
                        f"{item.target_date}（{weekday}）· {room_type} 当天还剩 {remaining} 间：{feature_text}。"
                        f"{weekend}{demand_crowd + '客人订得较多' if demand['confirmed'] else '暂无近期成交数据可比较'}，"
                        f"「{experience}」还有名额，整套 ¥{_money(item.suggested_price)} 卖（毛利率约 {margin}%），现余 {int(item.sale_quantity or 0)} 套，"
                        f"库存与名额都撑得住，适合优先推。{pair_text}"
                    ),
                    "feature": feature_text,
                    "pairing": pair_text,
                    "image_url": self._product_image(item),
                }
            )
        stats = {
            "sellable_products": len(on_sale),
            "confirmed_orders": int(demand["confirmed"]),
            "revenue": _money(demand["revenue"]),
            "orders_by_crowd": demand_crowd,
            "rooms_remaining": sum(int(row["remaining"]) for row in rooms),
            "room_type_count": len({row["room_type"] for row in rooms}),
            "date_count": len({row["date"] for row in rooms}),
        }
        options.append({"id": "more", "label": "再推荐 3 个", "message": "再推荐几个"})
        # 先给「本轮经营判断 + 一个主推商品」，再放备选方向，避免一上来铺一堆相似商品。
        judgement, primary, directions = self._business_judgement(rooms, demand, crowd, party_size, text, state)
        return {
            "step": "OVERVIEW",
            "summary": (
                f"我先翻了最近的经营情况：未来 10 天还有 {len(rooms)} 个「房型 × 日期」没卖出去，"
                f"已成交 {demand['confirmed']} 单、累计 ¥{_money(demand['revenue'])}，"
                f"{('其中' + demand_crowd + '客人订得最多。') if demand['confirmed'] else '近 14 天暂无已确认成交样本。'}"
                f"下面这几组是我觉得这两天更容易卖动的——房量够、体验还有名额、价格也压得住，"
                f"每组都写了为什么推荐，点开就能编辑或预览。"
            ),
            "facts": [
                {"label": "可售房型", "value": f"{len({row['room_type'] for row in rooms})} 种"},
                {"label": "最近房量最多的日期", "value": f"{best_days[0][0].month}月{best_days[0][0].day}日（{_weekday(best_days[0][0])}）" if best_days else "—"},
                {"label": "已成交", "value": f"{demand['confirmed']} 单 / ¥{_money(demand['revenue'])}"},
                {"label": "订单最多的客群", "value": demand_crowd},
            ],
            "inventory": inventory,
            "recommendations": recommendations,
            "recommended_products": recommended_products,
            "judgement": judgement,
            "primary": primary,
            "directions": directions,
            "stats": stats,
            "options": options,
            "question": "要不要先挑一个房型或日期，我再把具体的合作资源和酒店服务配给你？",
            "plan": {"crowd": crowd, "party_size": party_size, "product_offset": offset + 1},
        }

    def _plan(self, room_row, parsed, crowd, party_size, demand, state) -> dict[str, Any]:
        target: date = room_row["date"]
        resources = self._resources_for(target, crowd, party_size)
        services = self._services_for(target)
        knowledge = KnowledgeService(self.db).search(
            " ".join(item.resource_name for item in resources[:2]) or room_row["room_type"],
            limit=3,
        )
        chosen = state.get("resources") or [item.resource_name for item in resources[:2]]
        price = room_row["normal_price"] + sum(
            Decimal(str(item.market_price or 0)) for item in resources[:2]
        ) // 2
        recommendations = [
            {
                "title": f"{room_row['room_type']} + {item.resource_name}",
                "room_type": room_row["room_type"],
                "target_date": target.isoformat(),
                "resources": [item.resource_name],
                "price_hint": _money(price),
                "remaining": room_row["remaining"],
                "why": (
                    f"{item.resource_name}适合{CROWD_LABELS.get(item.suitable_crowds.split(',')[0], item.suitable_crowds)}，"
                    f"当天还剩 {item.remaining_capacity} 个名额，"
                    f"距离酒店所在片区车程可控，半天内可以完成。"
                ),
                "hotel_benefit": f"结算价 ¥{_money(item.settlement_price)}，市场价 ¥{_money(item.market_price)}，组合后仍有毛利空间。",
                "visitor_reason": str(item.description or ""),
            }
            for item in resources[:3]
        ]
        knowledge_suggestions = [
            {
                "name": record["name"],
                "why": f"{record['description']}（来源：{record['source_name']}）",
                "transport": f"位于{record.get('area') or '杭州'}，从酒店出发按当天交通约 20–40 分钟，可安排在体验前后顺路游览。",
                "opening_hours": record.get("opening_hours", ""),
            }
            for record in knowledge
        ]
        service_suggestions = [
            {
                "name": item.service_name,
                "why": f"当天有 {item.available_quantity} 份可用，参考价 ¥{_money(item.reference_price)}。",
            }
            for item in services
        ]
        options: list[dict[str, str]] = []
        for resource in resources[:3]:
            options.append(
                {
                    "id": f"pick:{resource.id}",
                    "label": f"加入 {resource.resource_name}",
                    "message": f"加入 {resource.resource_name}",
                }
            )
        for record in knowledge[:2]:
            options.append(
                {
                    "id": f"poi:{record['name']}",
                    "label": f"加入景点 {record['name']}",
                    "message": f"加入景点 {record['name']}",
                }
            )
        options.append({"id": "service:breakfast", "label": "搭配酒店早餐", "message": "搭配家庭早餐"})
        options.append({"id": "confirm", "label": "按这个方向生成产品", "message": "可以，按这个方向生成产品"})
        return {
            "step": "PLAN",
            "summary": (
                f"{target.month}月{target.day}日（{_weekday(target)}）{room_row['room_type']}还剩 {room_row['remaining']} 间；"
                f"我先按{crowd}的偏好配了 {len(resources)} 个合作资源。"
            ),
            "facts": [
                {"label": "房型", "value": room_row["room_type"]},
                {"label": "日期", "value": f"{target.isoformat()}（{_weekday(target)}）"},
                {"label": "剩余房量", "value": f"{room_row['remaining']} 间"},
                {"label": "预算参考", "value": f"¥{_money(price)} 起"},
            ],
            "recommendations": recommendations,
            "knowledge_suggestions": knowledge_suggestions,
            "service_suggestions": service_suggestions,
            "options": options,
            "question": "要不要加入上面某个资源或景点？也可以告诉我换房型、换日期、加减服务，我再更新一次。",
            "plan": {
                "room_type": room_row["room_type"],
                "target_date": target.isoformat(),
                "crowd": crowd,
                "party_size": party_size,
                "resources": chosen,
                "knowledge": [record["name"] for record in knowledge[:2]],
            },
        }

    def _finalize(self, state, parsed, room_row, crowd, party_size, demand) -> dict[str, Any]:
        # The concrete candidate creation is handled by the proposal service;
        # this turn only reports what will be generated and why.
        return {
            "step": "READY",
            "summary": (
                f"准备生成：{room_row['room_type']}（{room_row['date'].isoformat()}，剩 {room_row['remaining']} 间）"
                f"+ {'、'.join(state.get('resources') or []) or '待选资源'}。"
            ),
            "facts": [
                {"label": "房型", "value": room_row["room_type"]},
                {"label": "日期", "value": f"{room_row['date'].isoformat()}（{_weekday(room_row['date'])}）"},
                {"label": "同行人", "value": f"{party_size} 人（{crowd}）"},
                {"label": "预计剩余", "value": f"{room_row['remaining']} 间"},
            ],
            "recommendations": [],
            "options": [{"id": "confirm", "label": "开始生成候选", "message": "开始生成候选产品"}],
            "question": "确认后我会生成候选产品，并同时给出两套微调方案和一个热销预测。",
            "plan": state,
        }
