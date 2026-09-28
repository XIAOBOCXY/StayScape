"""Deterministic hotel operating insights for Agent planning.

The Agent receives summaries rather than raw guest data.  It may explain a
recommendation from these facts, but FastAPI remains responsible for prices,
inventory, capacity and any final product state.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import HotelService, Merchant, PartnerResource, RoomInventory, TravelProduct, VisitorIntent


class OperationsInsightService:
    def __init__(self, db: Session, hotel_id: int) -> None:
        self.db = db
        self.hotel_id = hotel_id

    def room_night_pressure(self, *, window_days: int = 10) -> dict[str, Any]:
        """未售房量汇总：未来若干天按「房型 × 日期」统计，供经营看板顶部指标使用。

        这里只做聚合，不解释、不预测；真正的容量与价格仍由产品生成链路计算。
        """

        today = date.today()
        horizon = today + timedelta(days=max(1, window_days))
        rooms = list(
            self.db.scalars(
                select(RoomInventory).where(
                    RoomInventory.hotel_id == self.hotel_id,
                    RoomInventory.available_date >= today,
                    RoomInventory.available_date < horizon,
                    RoomInventory.available_count > 0,
                    RoomInventory.status == "AVAILABLE",
                )
            ).all()
        )
        total = sum(int(room.available_count or 0) for room in rooms)
        focus = max(
            rooms,
            key=lambda room: int(room.available_count or 0) * Decimal(str(room.normal_price or 0)),
            default=None,
        )
        focus_date = focus.available_date if focus is not None else today
        resource_count = int(
            self.db.scalar(
                select(func.count())
                .select_from(PartnerResource)
                .join(Merchant)
                .where(
                    Merchant.hotel_id == self.hotel_id,
                    PartnerResource.available_date == focus_date,
                    PartnerResource.package_enabled.is_(True),
                    PartnerResource.remaining_capacity > 0,
                    PartnerResource.status == "AVAILABLE",
                )
            )
            or 0
        )
        return {
            "window_days": window_days,
            "unsold_room_nights": total,
            "room_type_count": len({str(room.room_type) for room in rooms}),
            "date_count": len({room.available_date for room in rooms}),
            "focus_room": (
                {
                    "room_type": str(focus.room_type),
                    "target_date": focus.available_date.isoformat(),
                    "remaining": int(focus.available_count or 0),
                }
                if focus is not None
                else None
            ),
            "available_resource_count": resource_count,
        }

    def snapshot(self, *, target_date: date, window_days: int = 14) -> dict[str, Any]:
        today = date.today()
        start = today - timedelta(days=max(1, window_days) - 1)
        products = list(
            self.db.scalars(
                select(TravelProduct)
                .where(TravelProduct.hotel_id == self.hotel_id)
                .options(selectinload(TravelProduct.resources))
            ).all()
        )
        intents = list(
            self.db.scalars(
                select(VisitorIntent)
                .join(TravelProduct)
                .where(TravelProduct.hotel_id == self.hotel_id, VisitorIntent.created_at >= start)
                .options(selectinload(VisitorIntent.product))
            ).all()
        )
        confirmed = [item for item in intents if item.reservation_status == "CONFIRMED" and item.product]
        candidate_intents = [item for item in intents if item.reservation_status in {"HELD", "CONFIRMED"} and item.product]
        theme_orders: Counter[str] = Counter()
        crowd_orders: Counter[str] = Counter()
        for item in confirmed:
            theme_orders[item.product.theme] += 1
            crowd_orders[item.product.target_crowd] += 1

        top_themes = [
            {"theme": name, "confirmed_orders": count}
            for name, count in theme_orders.most_common(3)
        ]
        top_crowds = [
            {"target_crowd": name, "confirmed_orders": count}
            for name, count in crowd_orders.most_common(3)
        ]
        rooms = list(
            self.db.scalars(
                select(RoomInventory).where(
                    RoomInventory.hotel_id == self.hotel_id,
                    RoomInventory.available_date == target_date,
                    RoomInventory.available_count > 0,
                    RoomInventory.status.not_in({"DISABLED", "SOLD_OUT"}),
                )
                .order_by(RoomInventory.available_count.desc())
            ).all()
        )
        partners = list(
            self.db.scalars(
                select(PartnerResource)
                .join(Merchant)
                .where(
                    Merchant.hotel_id == self.hotel_id,
                    PartnerResource.available_date == target_date,
                    PartnerResource.package_enabled.is_(True),
                    PartnerResource.remaining_capacity > 0,
                    PartnerResource.status == "AVAILABLE",
                )
                .order_by(PartnerResource.remaining_capacity.desc())
            ).all()
        )
        services = list(
            self.db.scalars(
                select(HotelService).where(
                    HotelService.hotel_id == self.hotel_id,
                    HotelService.available_date == target_date,
                    HotelService.available_quantity > 0,
                    HotelService.status == "AVAILABLE",
                )
                .order_by(HotelService.available_quantity.desc())
            ).all()
        )

        opportunity_rooms = [
            {"room_type": room.room_type, "available_count": room.available_count, "max_guests": room.max_guests}
            for room in rooms[:4]
        ]
        opportunity_resources = [
            {
                "name": resource.resource_name,
                "category": resource.category,
                "remaining_capacity": resource.remaining_capacity,
                "indoor": resource.indoor,
                "suitable_crowds": resource.suitable_crowds,
            }
            for resource in partners[:6]
        ]
        recommendations: list[dict[str, str]] = []
        if top_crowds:
            label = {"FAMILY": "亲子家庭", "COUPLE": "情侣", "FRIENDS": "朋友同行", "SOLO": "独自出行", "LOCAL_WEEKEND": "本地周末客"}.get(top_crowds[0]["target_crowd"], top_crowds[0]["target_crowd"])
            recommendations.append({"signal": "recent_demand", "message": f"近 {window_days} 天已确认订单中，{label}相关产品表现相对更好。"})
        if opportunity_rooms:
            recommendations.append({"signal": "inventory", "message": f"{target_date.isoformat()} 仍有可组合客房，优先从余量较高的房型中选择。"})
        if opportunity_resources:
            recommendations.append({"signal": "resource", "message": "合作资源中仍有可用名额，可组合为差异化体验，但以实时复核为准。"})
        if not recommendations:
            recommendations.append({"signal": "data_limited", "message": "当前经营样本有限，建议优先基于实时库存和已核验资源生成多套候选。"})

        revenue = sum((item.product.suggested_price for item in confirmed if item.product), Decimal("0"))
        gross_profit = sum((item.product.gross_profit for item in confirmed if item.product), Decimal("0"))
        return {
            "as_of": today.isoformat(),
            "window_days": window_days,
            "target_date": target_date.isoformat(),
            "confirmed_order_count": len(confirmed),
            "active_intent_count": len(candidate_intents),
            "confirmed_revenue": str(revenue),
            "confirmed_gross_profit": str(gross_profit),
            "intent_to_confirm_rate": round(len(confirmed) / len(candidate_intents), 4) if candidate_intents else None,
            "top_themes": top_themes,
            "top_crowds": top_crowds,
            "available_rooms": opportunity_rooms,
            "available_partner_resources": opportunity_resources,
            "available_services": [
                {"name": service.service_name, "type": service.service_type, "available_quantity": service.available_quantity}
                for service in services[:5]
            ],
            "recommendation_signals": recommendations,
            "data_quality": "FACTUAL_AGGREGATE",
        }
