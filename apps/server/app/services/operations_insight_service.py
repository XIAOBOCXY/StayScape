"""Deterministic hotel operating insights for Agent planning.

The Agent receives summaries rather than raw guest data.  It may explain a
recommendation from these facts, but FastAPI remains responsible for prices,
inventory, capacity and any final product state.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import HotelService, Merchant, PartnerResource, ProductResource, RoomInventory, TravelProduct, VisitorIntent


class OperationsInsightService:
    def __init__(self, db: Session, hotel_id: int) -> None:
        self.db = db
        self.hotel_id = hotel_id

    def room_night_pressure(self, *, window_days: int = 17) -> dict[str, Any]:
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
        unsold_value = sum((Decimal(str(room.available_count or 0)) * Decimal(str(room.normal_price or 0)) for room in rooms), Decimal("0"))
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
            "unsold_listed_value": str(unsold_value),
            "room_type_count": len({str(room.room_type) for room in rooms}),
            "date_count": len({room.available_date for room in rooms}),
            "focus_room": (
                {
                    "room_type": str(focus.room_type),
                    "target_date": focus.available_date.isoformat(),
                    "remaining": int(focus.available_count or 0),
                    "estimated_value": str(Decimal(str(focus.available_count or 0)) * Decimal(str(focus.normal_price or 0))),
                }
                if focus is not None
                else None
            ),
            "available_resource_count": resource_count,
        }

    def answer_query(self, question: str, *, window_days: int = 15) -> dict[str, Any]:
        """Answer common operating questions from persisted hotel records only.

        The returned context is also saved with the conversation so product
        planning can use the operator's focus on the next step.
        """
        today = date.today()
        start = today - timedelta(days=max(1, window_days) - 1)
        start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
        query = str(question or "").strip()
        normalized = query.lower()

        intents = list(self.db.scalars(
            select(VisitorIntent)
            .join(TravelProduct)
            .options(selectinload(VisitorIntent.product).selectinload(TravelProduct.resources))
            .where(
                TravelProduct.hotel_id == self.hotel_id,
                VisitorIntent.reservation_status == "CONFIRMED",
                or_(VisitorIntent.confirmed_at >= start_at, VisitorIntent.created_at >= start_at),
            )
        ).unique().all())
        confirmed = [
            item for item in intents
            if item.product is not None
            and start <= (item.confirmed_at or item.created_at).date() <= today
        ]

        def amount_for(item: VisitorIntent) -> tuple[Decimal, bool]:
            result = item.recommendation_result if isinstance(item.recommendation_result, dict) else {}
            submitted = result.get("submitted_price")
            if submitted is not None:
                try:
                    return Decimal(str(submitted)), False
                except Exception:
                    pass
            return Decimal(str(item.product.suggested_price or 0)), True

        product_totals: dict[int, dict[str, Any]] = {}
        crowd_totals: Counter[str] = Counter()
        total_revenue = Decimal("0")
        estimated_amounts = 0
        for item in confirmed:
            amount, estimated = amount_for(item)
            total_revenue += amount
            estimated_amounts += int(estimated)
            crowd_totals[str(item.product.target_crowd or "ALL")] += 1
            metric = product_totals.setdefault(item.product_id, {
                "name": item.product.product_name,
                "orders": 0,
                "revenue": Decimal("0"),
                "resources": Counter(),
            })
            metric["orders"] += 1
            metric["revenue"] += amount
            for resource in item.product.resources or []:
                if resource.resource_name:
                    metric["resources"][resource.resource_name] += 1

        product_rows = sorted(product_totals.values(), key=lambda row: (-row["orders"], -row["revenue"], row["name"]))
        crowd_labels = {"FAMILY": "亲子家庭", "COUPLE": "两人同行", "FRIENDS": "朋友同行", "SOLO": "独自出行", "LOCAL_WEEKEND": "本地周末客", "ALL": "不限客群"}
        top_crowd = crowd_totals.most_common(1)
        pressure = self.room_night_pressure(window_days=window_days)
        room_rows = list(self.db.scalars(
            select(RoomInventory).where(
                RoomInventory.hotel_id == self.hotel_id,
                RoomInventory.available_date >= today,
                RoomInventory.available_date < today + timedelta(days=window_days),
                RoomInventory.status == "AVAILABLE",
                RoomInventory.available_count > 0,
            ).order_by(RoomInventory.available_date, RoomInventory.available_count.desc())
        ).all())
        room_types: dict[str, int] = {}
        for room in room_rows:
            room_types[str(room.room_type)] = room_types.get(str(room.room_type), 0) + int(room.available_count or 0)
        insight = self.snapshot(target_date=today, window_days=window_days)

        if any(word in normalized for word in ("成交", "卖得", "销量", "销售", "产品", "订单", "客群")):
            if confirmed:
                product_text = "；".join(
                    f"{row['name']} {row['orders']} 单、成交约 ¥{row['revenue']:.2f}"
                    for row in product_rows[:3]
                ) or "暂无可按产品名称拆分的成交记录"
                crowd_text = "；".join(
                    f"{crowd_labels.get(code, '其他客群')} {count} 单"
                    for code, count in crowd_totals.most_common(3)
                )
                answer = (
                    f"近 {window_days} 天有 {len(confirmed)} 笔已确认订单，成交金额约 ¥{total_revenue:.2f}。"
                    f"按成交单数排序：{product_text}。客群分布：{crowd_text}。"
                    + (f"其中 {estimated_amounts} 笔缺少下单价格快照，金额按产品当前售价估算。" if estimated_amounts else "金额均来自订单提交时的价格记录。")
                )
            else:
                answer = f"近 {window_days} 天没有已确认订单，因此目前无法判断哪款产品或客群卖得最好；我不会用意向单或出行日期代替成交数据。"
            focus = "；".join(row["name"] for row in product_rows[:3]) or "近期产品成交样本有限"
            intent = "recent_sales"
        elif any(word in normalized for word in ("房态", "库存", "房量", "房型", "余量")) and not any(word in normalized for word in ("资源", "体验", "搭配", "权益")):
            top_rooms = sorted(room_types.items(), key=lambda row: (-row[1], row[0]))[:5]
            room_text = "；".join(f"{name} 当前可售 {count} 间夜" for name, count in top_rooms) or "未来日期暂无可售房量"
            date_text = "、".join(dict.fromkeys(room.available_date.isoformat() for room in room_rows[:8]))
            answer = (
                f"未来 {window_days} 天共有 {pressure['unsold_room_nights']} 间可售房晚，覆盖 {pressure['date_count']} 个日期、{pressure['room_type_count']} 种房型。{room_text}。"
                + (f"近期有库存的日期包括 {date_text}。" if date_text else "请先补充未来日期库存。")
                + "当前数据库记录的是实时可售量，没有每日总房量及历史入住快照，因此不能据此声称预测入住率或库存涨跌趋势。"
            )
            focus = room_text
            intent = "room_inventory"
        elif any(word in normalized for word in ("资源", "体验", "搭配", "权益")):
            rows = sorted(insight.get("resource_evidence") or [], key=lambda row: (-int(row.get("recent_confirmed_orders") or 0), -int(row.get("product_count") or 0), -int(row.get("remaining_capacity") or 0)))
            resource_text = "；".join(
                f"{row['name']} 可用 {row['remaining_capacity']} 份，进入 {row['product_count']} 个历史产品，近 15 天关联 {row['recent_confirmed_orders']} 笔成交"
                for row in rows[:5]
            ) or "当前日期范围内没有已启用组包且有余量的合作体验。"
            room = pressure.get("focus_room") or {}
            answer = f"未来 {window_days} 天的合作体验数据：{resource_text}。"
            if room:
                answer += f"当前待消化房量较多的是 {room.get('target_date')} 的{room.get('room_type')}（余 {room.get('remaining')} 间）；方案生成会优先检查同日可用资源、人数和容量。"
            focus = resource_text[:700]
            intent = "resource_fit"
        else:
            answer = (
                f"未来 {window_days} 天当前可售房晚 {pressure['unsold_room_nights']} 间，覆盖 {pressure['date_count']} 个日期；"
                f"近 {window_days} 天确认订单 {len(confirmed)} 笔、成交约 ¥{total_revenue:.2f}；"
                f"可组包合作体验 {len(insight.get('resource_evidence') or [])} 项。"
            )
            if top_crowd:
                answer += f"近期成交单数最多的是{crowd_labels.get(top_crowd[0][0], '其他客群')}（{top_crowd[0][1]} 单）。"
            else:
                answer += "近期没有足够的确认订单判断主力客群。"
            focus = query
            intent = "operations_overview"

        return {
            "answer": answer,
            "focus": focus,
            "intent": intent,
            "facts": {
                "window_days": window_days,
                "confirmed_orders": len(confirmed),
                "confirmed_revenue": str(total_revenue.quantize(Decimal("0.01"))),
                "estimated_amount_count": estimated_amounts,
                "room_nights": int(pressure["unsold_room_nights"]),
                "room_type_count": int(pressure["room_type_count"]),
                "resource_count": len(insight.get("resource_evidence") or []),
            },
        }

    def snapshot(self, *, target_date: date, window_days: int = 14) -> dict[str, Any]:
        today = date.today()
        start = today - timedelta(days=max(1, window_days) - 1)
        start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
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
                # 近期成交按确认时间统计，不按未来/过去的出行日期冒充下单时间。
                .where(
                    TravelProduct.hotel_id == self.hotel_id,
                    or_(VisitorIntent.confirmed_at >= start_at, VisitorIntent.created_at >= start_at),
                )
                .options(selectinload(VisitorIntent.product))
            ).all()
        )
        confirmed = [
            item for item in intents
            if item.reservation_status == "CONFIRMED" and item.product
            and (item.confirmed_at or item.created_at).date() >= start
            and (item.confirmed_at or item.created_at).date() <= today
        ]
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

        evidence_end = target_date + timedelta(days=15)
        evidence_resources = list(
            self.db.scalars(
                select(PartnerResource)
                .join(Merchant)
                .options(selectinload(PartnerResource.merchant))
                .where(
                    Merchant.hotel_id == self.hotel_id,
                    PartnerResource.available_date >= target_date,
                    PartnerResource.available_date < evidence_end,
                    PartnerResource.package_enabled.is_(True),
                    PartnerResource.remaining_capacity > 0,
                    PartnerResource.status == "AVAILABLE",
                )
                .order_by(PartnerResource.available_date, PartnerResource.resource_name)
            ).all()
        )
        evidence_services = list(
            self.db.scalars(
                select(HotelService)
                .where(
                    HotelService.hotel_id == self.hotel_id,
                    HotelService.available_date >= target_date,
                    HotelService.available_date < evidence_end,
                    HotelService.available_quantity > 0,
                    HotelService.status == "AVAILABLE",
                )
                .order_by(HotelService.available_date, HotelService.service_name)
            ).all()
        )
        resource_ids = [resource.id for resource in evidence_resources]
        product_use_counts: dict[int, int] = {}
        recent_sales_counts: dict[int, int] = {}
        if resource_ids:
            usage_rows = self.db.execute(
                select(ProductResource.resource_id, func.count(func.distinct(ProductResource.product_id)))
                .join(TravelProduct, TravelProduct.id == ProductResource.product_id)
                .where(
                    TravelProduct.hotel_id == self.hotel_id,
                    ProductResource.resource_type == "PARTNER_RESOURCE",
                    ProductResource.resource_id.in_(resource_ids),
                )
                .group_by(ProductResource.resource_id)
            ).all()
            product_use_counts = {int(resource_id): int(count) for resource_id, count in usage_rows}
            sales_rows = self.db.execute(
                select(ProductResource.resource_id, func.count(func.distinct(VisitorIntent.id)))
                .join(TravelProduct, TravelProduct.id == ProductResource.product_id)
                .join(VisitorIntent, VisitorIntent.product_id == TravelProduct.id)
                .where(
                    TravelProduct.hotel_id == self.hotel_id,
                    ProductResource.resource_type == "PARTNER_RESOURCE",
                    ProductResource.resource_id.in_(resource_ids),
                    VisitorIntent.reservation_status == "CONFIRMED",
                    or_(VisitorIntent.confirmed_at >= start_at, VisitorIntent.created_at >= start_at),
                )
                .group_by(ProductResource.resource_id)
            ).all()
            recent_sales_counts = {int(resource_id): int(count) for resource_id, count in sales_rows}

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
        resource_evidence = [
            {
                "id": resource.id,
                "name": resource.resource_name,
                "category": resource.category,
                "merchant_name": resource.merchant.merchant_name if resource.merchant else "",
                "available_date": resource.available_date.isoformat(),
                "remaining_capacity": int(resource.remaining_capacity or 0),
                "settlement_price": str(resource.settlement_price),
                "market_price": str(resource.market_price),
                "suitable_crowds": resource.suitable_crowds,
                "indoor": bool(resource.indoor),
                "address": resource.address,
                "product_count": product_use_counts.get(resource.id, 0),
                "recent_confirmed_orders": recent_sales_counts.get(resource.id, 0),
            }
            for resource in evidence_resources
        ]
        service_evidence = [
            {
                "id": service.id,
                "name": service.service_name,
                "type": service.service_type,
                "available_date": service.available_date.isoformat(),
                "available_quantity": int(service.available_quantity or 0),
                "unit_cost": str(service.unit_cost),
                "reference_price": str(service.reference_price),
                "suitable_crowds": service.suitable_crowds,
            }
            for service in evidence_services
        ]
        recommendations: list[dict[str, str]] = []
        if top_crowds:
            label = {"FAMILY": "亲子家庭", "COUPLE": "两人同行", "FRIENDS": "朋友同行", "SOLO": "独自出行", "LOCAL_WEEKEND": "本地周末客", "ALL": "不限客群"}.get(top_crowds[0]["target_crowd"], top_crowds[0]["target_crowd"])
            recommendations.append({"signal": "recent_demand", "message": f"近 {window_days} 天已确认订单中，{label}相关产品表现相对更好。"})
        if opportunity_rooms:
            recommendations.append({"signal": "inventory", "message": f"{target_date.isoformat()} 仍有可组合客房，优先从余量较高的房型中选择。"})
        if opportunity_resources:
            recommendations.append({"signal": "resource", "message": f"合作资源池有 {len(opportunity_resources)} 项可组合资源，推荐结果会同时校验日期、场次和剩余名额。"})
        if not recommendations:
            recommendations.append({"signal": "data_limited", "message": "当前经营样本有限，建议优先基于实时库存和已核验资源生成多套候选。"})

        def order_amount(item: VisitorIntent) -> tuple[Decimal, bool]:
            snapshot = item.recommendation_result if isinstance(item.recommendation_result, dict) else {}
            submitted = snapshot.get("submitted_price")
            if submitted is not None:
                try:
                    return Decimal(str(submitted)), False
                except Exception:
                    pass
            return Decimal(str(item.product.suggested_price or 0)), True

        amount_pairs = [order_amount(item) for item in confirmed]
        revenue = sum((amount for amount, _ in amount_pairs), Decimal("0"))
        gross_profit = sum((item.product.gross_profit for item in confirmed if item.product), Decimal("0"))
        return {
            "as_of": today.isoformat(),
            "window_days": window_days,
            "target_date": target_date.isoformat(),
            "confirmed_order_count": len(confirmed),
            "active_intent_count": len(candidate_intents),
            "confirmed_revenue": str(revenue),
            "estimated_amount_count": sum(1 for _, estimated in amount_pairs if estimated),
            "confirmed_gross_profit": str(gross_profit),
            "intent_to_confirm_rate": round(len(confirmed) / len(candidate_intents), 4) if candidate_intents else None,
            "top_themes": top_themes,
            "top_crowds": top_crowds,
            "available_rooms": opportunity_rooms,
            "available_partner_resources": opportunity_resources,
            "resource_evidence": resource_evidence,
            "service_evidence": service_evidence,
            "available_services": [
                {"name": service.service_name, "type": service.service_type, "available_quantity": service.available_quantity}
                for service in services[:5]
            ],
            "recommendation_signals": recommendations,
            "data_quality": "FACTUAL_AGGREGATE",
        }
