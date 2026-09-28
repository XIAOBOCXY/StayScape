"""Auditable opportunity briefing for the 余宿成景 operating Skill.

This service deliberately returns factual inputs and bounded directions, not a
model-made product.  Product creation remains in ProductProposalService, where
FastAPI owns price, capacity, time and publish validation.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Hotel, HotelService, Merchant, PartnerResource, RoomInventory
from ..rules.availability_rule import resource_is_usable
from ..rules.crowd_rule import crowd_supported
from ..rules.weather_rule import is_weather_supported
from .knowledge_service import KnowledgeService
from .operations_insight_service import OperationsInsightService
from .weather_service import WeatherService


_CROWD_LABELS = {
    "FAMILY": "亲子家庭",
    "COUPLE": "情侣/双人客",
    "FRIENDS": "年轻朋友结伴",
    "SOLO": "独自出行",
    "LOCAL_WEEKEND": "本地周末微度假",
}
_DEFAULT_CROWDS = ("FAMILY", "COUPLE", "FRIENDS", "LOCAL_WEEKEND")


class HotelOpportunityService:
    def __init__(self, db: Session, hotel_id: int) -> None:
        self.db = db
        self.hotel_id = hotel_id

    @staticmethod
    def _room_context(room: RoomInventory, *, largest_remaining: int) -> dict[str, Any]:
        relative_surplus = round(room.available_count / max(1, largest_remaining), 4)
        return {
            "room_inventory_id": room.id,
            "room_type": room.room_type,
            "available_count": room.available_count,
            "max_guests": room.max_guests,
            "suitable_crowds": room.suitable_crowds,
            "relative_surplus_score": relative_surplus,
            "reason": f"该房型当日可用 {room.available_count} 间；相对余量分用于排序，不等同于总库存压力。",
        }

    @staticmethod
    def _service_context(service: HotelService) -> dict[str, Any]:
        return {
            "id": service.id,
            "service_name": service.service_name,
            "service_type": service.service_type,
            "available_quantity": service.available_quantity,
            "start_time": service.start_time.isoformat() if service.start_time else None,
            "end_time": service.end_time.isoformat() if service.end_time else None,
            "suitable_crowds": service.suitable_crowds,
            "status": service.status,
        }

    @staticmethod
    def _resource_context(resource: PartnerResource, *, weather_status: str) -> dict[str, Any]:
        return {
            "id": resource.id,
            "resource_name": resource.resource_name,
            "category": resource.category,
            "description": resource.description,
            "available_date": resource.available_date.isoformat(),
            "start_time": resource.start_time.isoformat() if resource.start_time else None,
            "end_time": resource.end_time.isoformat() if resource.end_time else None,
            "remaining_capacity": resource.remaining_capacity,
            "suitable_crowds": resource.suitable_crowds,
            "minimum_age": resource.minimum_age,
            "maximum_age": resource.maximum_age,
            "indoor": resource.indoor,
            "weather_tags": resource.weather_tags,
            "address": resource.address,
            "booking_notice": resource.booking_notice,
            "source_type": resource.source_type,
            "weather_check": weather_status,
            "formal_package_eligible": True,
        }

    def analyze(
        self,
        *,
        target_date: date,
        target_crowd: str = "",
        party_size: int = 0,
        theme: str = "",
        knowledge_query: str = "",
        direction_limit: int = 4,
    ) -> dict[str, Any]:
        hotel = self.db.get(Hotel, self.hotel_id)
        if not hotel or hotel.status != "ACTIVE":
            raise ValueError("active hotel is required")
        weather = WeatherService(self.db).get_forecast(hotel.city, target_date)
        weather_active = bool(weather.get("usable"))
        weather_scenario = str(weather.get("scenario") or "CLOUDY")
        party_size = max(0, party_size)
        rooms = list(
            self.db.scalars(
                select(RoomInventory)
                .where(
                    RoomInventory.hotel_id == self.hotel_id,
                    RoomInventory.available_date == target_date,
                    RoomInventory.available_count > 0,
                    RoomInventory.status.not_in({"SOLD_OUT", "DISABLED"}),
                )
                .order_by(RoomInventory.available_count.desc(), RoomInventory.id)
            ).all()
        )
        if party_size:
            rooms = [item for item in rooms if item.max_guests >= party_size]
        largest_remaining = max((item.available_count for item in rooms), default=1)
        room_context = [self._room_context(item, largest_remaining=largest_remaining) for item in rooms]

        services = list(
            self.db.scalars(
                select(HotelService)
                .where(
                    HotelService.hotel_id == self.hotel_id,
                    HotelService.available_date == target_date,
                    HotelService.available_quantity > 0,
                    HotelService.status == "AVAILABLE",
                )
                .order_by(HotelService.available_quantity.desc(), HotelService.id)
            ).all()
        )
        if target_crowd:
            services = [item for item in services if crowd_supported(item.suitable_crowds, target_crowd)]

        resources = list(
            self.db.scalars(
                select(PartnerResource)
                .join(Merchant)
                .options(selectinload(PartnerResource.merchant))
                .where(
                    Merchant.hotel_id == self.hotel_id,
                    PartnerResource.available_date == target_date,
                    PartnerResource.remaining_capacity > 0,
                )
                .order_by(PartnerResource.remaining_capacity.desc(), PartnerResource.id)
            ).unique().all()
        )
        eligible_resources: list[PartnerResource] = []
        for resource in resources:
            merchant = resource.merchant
            if not merchant or not resource_is_usable(
                merchant_status=merchant.cooperation_status,
                package_enabled=resource.package_enabled,
                resource_status=resource.status,
                capacity=resource.remaining_capacity,
                source_type=resource.source_type,
            ):
                continue
            if party_size and resource.remaining_capacity < party_size:
                continue
            if target_crowd and not crowd_supported(
                resource.suitable_crowds,
                target_crowd,
                minimum_age=resource.minimum_age,
                maximum_age=resource.maximum_age,
            ):
                continue
            if weather_active and not is_weather_supported(resource.weather_tags, weather_scenario):
                continue
            eligible_resources.append(resource)

        insights = OperationsInsightService(self.db, self.hotel_id).snapshot(target_date=target_date)
        inferred_crowds = [item["target_crowd"] for item in insights.get("top_crowds") or [] if item.get("target_crowd")]
        crowd_candidates = [target_crowd] if target_crowd else list(dict.fromkeys(inferred_crowds + list(_DEFAULT_CROWDS)))
        directions: list[dict[str, Any]] = []
        for resource in eligible_resources:
            candidate_crowd = next(
                (
                    crowd
                    for crowd in crowd_candidates
                    if crowd_supported(
                        resource.suitable_crowds,
                        crowd,
                        minimum_age=resource.minimum_age,
                        maximum_age=resource.maximum_age,
                    )
                ),
                "",
            )
            if not candidate_crowd:
                continue
            directions.append(
                {
                    "target_crowd": candidate_crowd,
                    "target_crowd_label": _CROWD_LABELS.get(candidate_crowd, candidate_crowd),
                    "theme_hint": theme.strip() or resource.category,
                    "core_resource_id": resource.id,
                    "core_resource_name": resource.resource_name,
                    "room_options": room_context[:3],
                    "reason": (
                        f"{resource.resource_name}在 {target_date.isoformat()} 仍有 {resource.remaining_capacity} 个可用名额，"
                        f"适配 {resource.category}；正式容量、价格和时间仍须由候选创建工具复核。"
                    ),
                }
            )
            if len(directions) >= max(1, min(direction_limit, 8)):
                break
        query = " ".join(item for item in (knowledge_query, theme, target_crowd) if item.strip())
        knowledge = KnowledgeService(self.db).search(
            query,
            target_crowd=target_crowd,
            weather=weather_scenario if weather_active else "",
            limit=12,
        )
        return {
            "target_date": target_date.isoformat(),
            "party_size": party_size or None,
            "weather": weather,
            "inventory_opportunities": room_context,
            "recent_demand": {
                "window_days": insights.get("window_days"),
                "confirmed_order_count": insights.get("confirmed_order_count"),
                "top_themes": insights.get("top_themes"),
                "top_crowds": insights.get("top_crowds"),
                "recommendation_signals": insights.get("recommendation_signals"),
                "data_quality": insights.get("data_quality"),
            },
            "eligible_hotel_services": [self._service_context(item) for item in services],
            "eligible_partner_resources": [
                self._resource_context(item, weather_status="ACTIVE" if weather_active else "VERIFY_REQUIRED")
                for item in eligible_resources
            ],
            "candidate_directions": directions,
            "travel_knowledge": knowledge,
            "knowledge_notice": "文旅知识仅作带来源的公共路线参考，不能作为已预约或可售权益。",
            "data_sources": [
                "酒店实时库存与服务",
                "合作资源可用状态",
                "近 14 天去标识化经营聚合",
                "带来源天气预报",
                "带来源杭州文旅知识库",
            ],
            "notices": [
                "候选方向不是已创建产品；创建后仍需完成 FastAPI 的容量、价格、年龄、天气与时间复核。",
                "天气状态为 VERIFY_REQUIRED 时，不将天气作为已确认事实，也不据此自动发布产品。",
            ] if not weather_active else [
                "候选方向不是已创建产品；创建后仍需完成 FastAPI 的容量、价格、年龄、天气与时间复核。",
            ],
        }
