from datetime import date, time
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..agent import AgentOrchestrator
from ..agent.schemas import ProductAgentOutput
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
from .inventory_service import ensure_publish_capacity, reconcile_published_capacity


DEFAULT_QUANTITIES = {"BREAKFAST": 3, "LATE_CHECKOUT": 1}
NON_EXCLUSIVE_SERVICE_TYPES = {"BREAKFAST", "PARKING", "LUGGAGE_STORAGE", "LATE_CHECKOUT"}


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
    def __init__(self, db: Session, hotel_id: int, orchestrator: AgentOrchestrator | None = None) -> None:
        self.db = db
        self.hotel_id = hotel_id
        self.orchestrator = orchestrator or AgentOrchestrator(db, hotel_id=hotel_id)

    def ensure_publish_capacity(self, product: TravelProduct) -> list[dict[str, Any]]:
        return ensure_publish_capacity(self.db, product)

    def _room(self, request: GenerateProductRequest) -> RoomInventory:
        query = select(RoomInventory).where(RoomInventory.hotel_id == self.hotel_id, RoomInventory.available_date == request.target_date)
        if request.room_inventory_id:
            query = query.where(RoomInventory.id == request.room_inventory_id)
        room = self.db.scalar(query.order_by(RoomInventory.available_count.desc()))
        if not room:
            raise AppError("ROOM_INVENTORY_INSUFFICIENT", "没有找到符合入住日期的临期客房", field="room_inventory_id", retryable=True)
        if room.available_count <= 0 or room.status in {"SOLD_OUT", "DISABLED"}:
            raise AppError("ROOM_INVENTORY_INSUFFICIENT", "客房库存不足或已停用", field="room_inventory_id", retryable=True)
        return room

    def _default_selections(self, request: GenerateProductRequest, room: RoomInventory) -> list[dict[str, Any]]:
        selections: list[dict[str, Any]] = []
        services = list(self.db.scalars(select(HotelService).where(HotelService.hotel_id == self.hotel_id, HotelService.available_date == request.target_date, HotelService.status == "AVAILABLE").order_by(HotelService.id)).all())
        breakfast = next((item for item in services if item.service_type == "BREAKFAST"), None)
        late_checkout = next((item for item in services if item.service_type == "LATE_CHECKOUT"), None)
        if breakfast:
            selections.append({"resource_type": "HOTEL_SERVICE", "resource_id": breakfast.id, "quantity_per_package": 3})
        if late_checkout:
            selections.append({"resource_type": "HOTEL_SERVICE", "resource_id": late_checkout.id, "quantity_per_package": 1})
        partners = list(self.db.scalars(select(PartnerResource).join(Merchant).where(Merchant.hotel_id == self.hotel_id, PartnerResource.available_date == request.target_date).order_by(PartnerResource.id)).all())
        eligible = [item for item in partners if self._partner_candidate(item, request)]
        if request.weather == "RAIN":
            eligible.sort(key=lambda item: (not item.indoor, item.settlement_price, item.id))
        elif request.weather == "SUNNY":
            eligible.sort(key=lambda item: (item.indoor, item.settlement_price, item.id))
        else:
            eligible.sort(key=lambda item: (not item.indoor, item.settlement_price, item.id))
        selected = eligible[0] if eligible else None
        if selected:
            selections.append({"resource_type": "PARTNER_RESOURCE", "resource_id": selected.id, "quantity_per_package": 3 if selected.category == "CULTURE" else 1})
        return selections

    def _partner_candidate(self, resource: PartnerResource, request: GenerateProductRequest) -> bool:
        merchant = resource.merchant
        return bool(
            merchant
            and resource.available_date == request.target_date
            and resource_is_usable(merchant_status=merchant.cooperation_status, package_enabled=resource.package_enabled, resource_status=resource.status, capacity=resource.remaining_capacity)
            and crowd_supported(resource.suitable_crowds, request.target_crowd, minimum_age=resource.minimum_age, maximum_age=resource.maximum_age)
            and is_weather_supported(resource.weather_tags, request.weather)
        )

    def _payload(self, request: GenerateProductRequest, room: RoomInventory, selections: list[dict[str, Any]], *, variant_index: int = 0) -> dict[str, Any]:
        services = list(self.db.scalars(select(HotelService).where(HotelService.hotel_id == self.hotel_id, HotelService.available_date == request.target_date)).all())
        partners = list(self.db.scalars(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(Merchant.hotel_id == self.hotel_id, PartnerResource.available_date == request.target_date)).unique().all())
        return {
            "hotel_id": self.hotel_id,
            "target_date": request.target_date.isoformat(),
            "weather": request.weather,
            "target_crowd": request.target_crowd,
            "theme": request.theme,
            "creative_direction": request.creative_direction,
            "variant_index": variant_index,
            "variant_total": request.variant_count,
            "visitor_budget": str(request.visitor_budget),
            "preferred_price": str(request.preferred_price),
            "room_inventory": {"id": room.id, "room_type": room.room_type, "max_guests": room.max_guests, "features": room.features, "available_count": room.available_count},
            "requested_selections": selections,
            "allowed_hotel_services": [{"id": item.id, "service_name": item.service_name, "service_type": item.service_type, "status": item.status, "start_time": item.start_time.strftime("%H:%M") if item.start_time else None, "end_time": item.end_time.strftime("%H:%M") if item.end_time else None, "unit_cost": str(item.unit_cost)} for item in services if item.status == "AVAILABLE"],
            "allowed_partner_resources": [{"id": item.id, "resource_name": item.resource_name, "category": item.category, "description": item.description, "address": item.address, "start_time": item.start_time.strftime("%H:%M") if item.start_time else None, "end_time": item.end_time.strftime("%H:%M") if item.end_time else None, "remaining_capacity": item.remaining_capacity, "settlement_price": str(item.settlement_price), "indoor": item.indoor, "suitable_crowds": item.suitable_crowds, "weather_tags": item.weather_tags, "status": item.status, "package_enabled": item.package_enabled, "merchant_status": item.merchant.cooperation_status if item.merchant else "TERMINATED"} for item in partners if item.merchant and item.merchant.cooperation_status == "ACTIVE" and item.package_enabled and item.status == "AVAILABLE"],
        }

    def generate(self, request: GenerateProductRequest, *, variant_index: int = 0) -> tuple[TravelProduct, dict[str, Any], str, bool]:
        room = self._room(request)
        selections = [item.model_dump() for item in request.resource_selections] or self._default_selections(request, room)
        payload = self._payload(request, room, selections, variant_index=variant_index)
        agent_result = self.orchestrator.generate_product(payload)
        output: ProductAgentOutput = agent_result.value  # type: ignore[assignment]
        if output.room_inventory_id != room.id:
            raise AppError("AGENT_RESOURCE_ID_INVALID", "Agent选择了不在请求范围内的客房资源", field="room_inventory_id")
        requested_by_type = {(item["resource_type"], item["resource_id"]): item for item in selections}
        selected_services = [item.id for item in self.db.scalars(select(HotelService).where(HotelService.id.in_(output.hotel_service_ids), HotelService.hotel_id == self.hotel_id)).all()] if output.hotel_service_ids else []
        selected_partners = list(self.db.scalars(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(PartnerResource.id.in_(output.partner_resource_ids), Merchant.hotel_id == self.hotel_id)).unique().all()) if output.partner_resource_ids else []
        if set(selected_services) != set(output.hotel_service_ids) or set(item.id for item in selected_partners) != set(output.partner_resource_ids):
            raise AppError("AGENT_RESOURCE_ID_INVALID", "Agent返回了不存在或不属于当前酒店的资源ID", field="resource_ids")
        for resource_type, resource_id in [("HOTEL_SERVICE", item) for item in selected_services] + [("PARTNER_RESOURCE", item.id) for item in selected_partners]:
            if requested_by_type and (resource_type, resource_id) not in requested_by_type and request.resource_selections:
                raise AppError("AGENT_RESOURCE_ID_INVALID", "Agent选择了未授权的资源ID", field="resource_ids")

        services = [self.db.get(HotelService, item) for item in selected_services]
        resource_rows: list[ProductResource] = [ProductResource(resource_type="ROOM", resource_id=room.id, resource_name=room.room_type, quantity_per_package=1, unit_cost=room.accounting_cost, replaceable=False, required=True)]
        capacity_inputs = [CapacityInput(room.room_type, room.available_count, 1)]
        unit_cost = room.accounting_cost
        warnings: list[str] = []
        schedule_slots: list[tuple[time | None, time | None, str]] = []
        for service in services:
            if service is None:
                continue
            q = output.resource_quantities.get(str(service.id), requested_by_type.get(("HOTEL_SERVICE", service.id), {}).get("quantity_per_package", DEFAULT_QUANTITIES.get(service.service_type, 1)))
            self._validate_service(service, request, q)
            if blocks_schedule(service) and any(intervals_overlap(service.start_time, service.end_time, start, end) for start, end, _ in schedule_slots):
                raise AppError("TIME_CONFLICT", f"酒店服务{service.service_name}与套餐内其他活动时间冲突", field="resource_selections", retryable=True)
            resource_rows.append(ProductResource(resource_type="HOTEL_SERVICE", resource_id=service.id, resource_name=service.service_name, quantity_per_package=q, unit_cost=service.unit_cost, replaceable=service.replaceable, required=True))
            capacity_inputs.append(CapacityInput(service.service_name, service.available_quantity, q))
            unit_cost += service.unit_cost * q
            if blocks_schedule(service):
                schedule_slots.append((service.start_time, service.end_time, service.service_name))
        for partner in selected_partners:
            q = output.resource_quantities.get(str(partner.id), requested_by_type.get(("PARTNER_RESOURCE", partner.id), {}).get("quantity_per_package", 1))
            self._validate_partner(partner, request, q)
            if any(intervals_overlap(partner.start_time, partner.end_time, start, end) for start, end, _ in schedule_slots):
                raise AppError("TIME_CONFLICT", f"文化体验{partner.resource_name}与套餐内其他活动时间冲突", field="resource_selections", retryable=True)
            resource_rows.append(ProductResource(resource_type="PARTNER_RESOURCE", resource_id=partner.id, resource_name=partner.resource_name, quantity_per_package=q, unit_cost=partner.settlement_price, replaceable=True, required=True))
            capacity_inputs.append(CapacityInput(partner.resource_name, partner.remaining_capacity, q))
            unit_cost += partner.settlement_price * q
            schedule_slots.append((partner.start_time, partner.end_time, partner.resource_name))
        if len(resource_rows) < 2:
            raise AppError("VALIDATION_ERROR", "套餐至少需要客房和一项酒店服务或文旅体验", field="resource_selections")
        validation = validate_package(capacity_inputs=capacity_inputs, unit_cost=unit_cost, room_minimum_price=room.minimum_price, minimum_gross_margin=request.minimum_gross_margin, visitor_budget=request.visitor_budget, preferred_price=request.preferred_price, warnings=warnings)
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
            weather=request.weather,
            target_date=request.target_date,
            room_inventory_id=room.id,
            sale_quantity=validation.capacity.sale_quantity,
            unit_cost=validation.pricing.unit_cost,
            minimum_allowed_price=validation.pricing.minimum_allowed_price,
            suggested_price=validation.pricing.suggested_price,
            gross_profit=validation.pricing.gross_profit,
            gross_margin=validation.pricing.gross_margin,
            minimum_gross_margin_requirement=request.minimum_gross_margin,
            visitor_budget_limit=request.visitor_budget,
            price_anchor=request.preferred_price,
            bottleneck_resource=validation.capacity.bottleneck_resource,
            marketing_title=output.marketing_title,
            marketing_content=output.marketing_content,
            marketing_assets=[item.model_dump(mode="json") for item in output.marketing_assets],
            recommendation_reason=output.recommendation_reason,
            risk_message=output.risk_message,
            status="DRAFT",
            resources=resource_rows,
        )
        self.db.add(product)
        self.db.flush()
        return product, validation.as_dict(), agent_result.trace_id, agent_result.fallback_used

    def generate_many(self, request: GenerateProductRequest) -> list[tuple[TravelProduct, dict[str, Any], str, bool]]:
        """Generate several creative candidates over the same real inventory snapshot.

        Each candidate is independently validated and persisted as a draft. The
        business numbers remain deterministic and identical when the resource
        selections are identical; only the creative packaging varies.
        """
        return [self.generate(request, variant_index=index) for index in range(request.variant_count)]

    def _marketing_payload(self, product: TravelProduct, creative_direction: str = "") -> dict[str, Any]:
        room = self.db.get(RoomInventory, product.room_inventory_id)
        selections = [{"resource_type": row.resource_type, "resource_id": row.resource_id, "quantity_per_package": row.quantity_per_package} for row in product.resources if row.resource_type != "ROOM"]
        request = GenerateProductRequest(
            target_date=product.target_date,
            weather=product.weather,
            target_crowd=product.target_crowd,
            theme=product.theme,
            room_inventory_id=product.room_inventory_id,
            resource_selections=selections,
            preferred_price=product.price_anchor,
            visitor_budget=product.visitor_budget_limit,
            minimum_gross_margin=product.minimum_gross_margin_requirement,
            variant_count=1,
            creative_direction=creative_direction,
        )
        return self._payload(request, room, selections)

    def regenerate_marketing(self, product: TravelProduct, creative_direction: str = "") -> tuple[str, bool]:
        result = self.orchestrator.generate_product(self._marketing_payload(product, creative_direction))
        output: ProductAgentOutput = result.value  # type: ignore[assignment]
        product.marketing_title = output.marketing_title
        product.marketing_content = output.marketing_content
        product.recommendation_reason = output.recommendation_reason
        product.risk_message = output.risk_message
        product.marketing_assets = [item.model_dump(mode="json") for item in output.marketing_assets]
        self.db.flush()
        return result.trace_id, result.fallback_used

    def _validate_service(self, service: HotelService, request: GenerateProductRequest, quantity: int) -> None:
        if quantity <= 0:
            raise AppError("VALIDATION_ERROR", "每套服务消耗量必须大于0", field=f"service_{service.id}")
        if service.available_date != request.target_date or service.status != "AVAILABLE" or service.available_quantity <= 0:
            raise AppError("HOTEL_SERVICE_UNAVAILABLE", f"酒店服务{service.service_name}当前不可用", field="resource_selections", retryable=True)
        if not crowd_supported(service.suitable_crowds, request.target_crowd):
            raise AppError("CROWD_NOT_SUPPORTED", f"酒店服务{service.service_name}不适合当前客群", field="target_crowd", retryable=True)
        validate_interval(service.start_time, service.end_time, service.service_name)

    def _validate_partner(self, partner: PartnerResource, request: GenerateProductRequest, quantity: int) -> None:
        if quantity <= 0:
            raise AppError("VALIDATION_ERROR", "每套体验消耗量必须大于0", field=f"resource_{partner.id}")
        merchant = partner.merchant
        if not merchant or not resource_is_usable(merchant_status=merchant.cooperation_status, package_enabled=partner.package_enabled, resource_status=partner.status, capacity=partner.remaining_capacity):
            raise AppError("PARTNER_RESOURCE_UNAVAILABLE", f"合作资源{partner.resource_name}当前不可组包", field="resource_selections", retryable=True)
        if partner.available_date != request.target_date:
            raise AppError("DATE_NOT_MATCHED", "合作资源日期与入住日期不一致", field="target_date", retryable=True)
        if not is_weather_supported(partner.weather_tags, request.weather):
            raise AppError("WEATHER_NOT_SUPPORTED", f"{partner.resource_name}不支持当前天气", field="weather", retryable=True)
        if not crowd_supported(partner.suitable_crowds, request.target_crowd, minimum_age=partner.minimum_age, maximum_age=partner.maximum_age):
            raise AppError("CROWD_NOT_SUPPORTED", f"{partner.resource_name}不适合当前客群", field="target_crowd", retryable=True)
        validate_interval(partner.start_time, partner.end_time, partner.resource_name)

    def recalculate_for_event(self, event: ResourceChangeEvent) -> list[dict[str, Any]]:
        references: list[TravelProduct] = []
        if event.resource_type == "PARTNER_RESOURCE":
            references = [item for item in products_referencing(self.db, "PARTNER_RESOURCE", event.resource_id) if item.hotel_id == self.hotel_id]
        elif event.resource_type == "HOTEL_SERVICE":
            references = [item for item in products_referencing(self.db, "HOTEL_SERVICE", event.resource_id) if item.hotel_id == self.hotel_id]
        elif event.resource_type == "ROOM":
            references = list(self.db.scalars(select(TravelProduct).options(selectinload(TravelProduct.resources), selectinload(TravelProduct.adjustments)).where(TravelProduct.room_inventory_id == event.resource_id, TravelProduct.hotel_id == self.hotel_id)).unique().all())
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
        capacity_inputs = [CapacityInput(room.room_type, room.available_count, 1)]
        unit_cost = room.accounting_cost
        invalid_reason = None
        partner_row = None
        schedule_slots: list[tuple[time | None, time | None, str]] = []
        for row in rows:
            if row.resource_type == "ROOM":
                continue
            if row.resource_type == "HOTEL_SERVICE":
                service = self.db.get(HotelService, row.resource_id)
                if not service or service.available_date != product.target_date or service.status != "AVAILABLE" or service.available_quantity <= 0:
                    invalid_reason = f"酒店服务{row.resource_name}不可用"
                    break
                if service.start_time and service.end_time and service.start_time >= service.end_time:
                    invalid_reason = f"酒店服务{row.resource_name}时间无效"
                    break
                if not crowd_supported(service.suitable_crowds, product.target_crowd):
                    invalid_reason = f"酒店服务{row.resource_name}不适合当前客群"
                    break
                if blocks_schedule(service) and any(intervals_overlap(service.start_time, service.end_time, start, end) for start, end, _ in schedule_slots):
                    invalid_reason = f"酒店服务{row.resource_name}与套餐内其他活动时间冲突"
                    break
                capacity_inputs.append(CapacityInput(service.service_name, service.available_quantity, row.quantity_per_package))
                unit_cost += service.unit_cost * row.quantity_per_package
                row.unit_cost = service.unit_cost
                if blocks_schedule(service):
                    schedule_slots.append((service.start_time, service.end_time, service.service_name))
            elif row.resource_type == "PARTNER_RESOURCE":
                partner_row = row
                partner = self.db.get(PartnerResource, row.resource_id)
                merchant = self.db.get(Merchant, partner.merchant_id) if partner else None
                if not partner or not merchant or partner.available_date != product.target_date or not resource_is_usable(merchant_status=merchant.cooperation_status, package_enabled=partner.package_enabled, resource_status=partner.status, capacity=partner.remaining_capacity):
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
                if partner.available_date != product.target_date:
                    invalid_reason = f"{partner.resource_name}日期与产品入住日期不一致"
                    break
                if not is_weather_supported(partner.weather_tags, product.weather):
                    replacement = self._find_replacement(product, row, room, capacity_inputs, unit_cost)
                    if replacement:
                        replacement_id = replacement.id
                        row.resource_id = replacement.id
                        row.resource_name = replacement.resource_name
                        row.unit_cost = replacement.settlement_price
                        partner = replacement
                    else:
                        invalid_reason = f"{partner.resource_name}不支持产品天气{product.weather}且没有替代资源"
                        break
                if not crowd_supported(partner.suitable_crowds, product.target_crowd, minimum_age=partner.minimum_age, maximum_age=partner.maximum_age):
                    replacement = self._find_replacement(product, row, room, capacity_inputs, unit_cost)
                    if replacement:
                        replacement_id = replacement.id
                        row.resource_id = replacement.id
                        row.resource_name = replacement.resource_name
                        row.unit_cost = replacement.settlement_price
                        partner = replacement
                    else:
                        invalid_reason = f"{partner.resource_name}不适合产品客群且没有替代资源"
                        break
                if any(intervals_overlap(partner.start_time, partner.end_time, start, end) for start, end, _ in schedule_slots):
                    replacement = self._find_replacement(product, row, room, capacity_inputs, unit_cost)
                    if replacement and not any(intervals_overlap(replacement.start_time, replacement.end_time, start, end) for start, end, _ in schedule_slots):
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
                schedule_slots.append((partner.start_time, partner.end_time, partner.resource_name))
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
                room_minimum_price=room.minimum_price,
                minimum_gross_margin=product.minimum_gross_margin_requirement,
                visitor_budget=product.visitor_budget_limit,
                preferred_price=product.price_anchor,
            )
        except AppError as exc:
            product.sale_quantity = 0
            product.status = "PAUSED"
            return self._record_adjustment(product, event, old_quantity, old_price, "PAUSE_PRODUCT", exc.message, replacement_id)
        product.sale_quantity = validation.capacity.sale_quantity
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
        reason = replacement_message or f"资源变化后重新计算：{old_quantity}套→{product.sale_quantity}套"
        return self._record_adjustment(product, event, old_quantity, old_price, action, reason, replacement_id)

    def _find_replacement(self, product: TravelProduct, row: ProductResource, room: RoomInventory, existing_capacity: list[CapacityInput], existing_cost: Decimal) -> PartnerResource | None:
        old = self.db.get(PartnerResource, row.resource_id)
        if not old:
            return None
        candidates = list(self.db.scalars(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(Merchant.hotel_id == self.hotel_id, PartnerResource.id != old.id, PartnerResource.available_date == product.target_date, PartnerResource.category == old.category, PartnerResource.package_enabled.is_(True), PartnerResource.status == "AVAILABLE", Merchant.cooperation_status == "ACTIVE").order_by(PartnerResource.settlement_price)).unique().all())
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
                if source is not None and (not isinstance(source, HotelService) or blocks_schedule(source))
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
        record = ProductAdjustmentRecord(product_id=product.id, change_event_id=event.id if event else None, old_quantity=old_quantity, new_quantity=product.sale_quantity, old_price=old_price, new_price=product.suggested_price, action=action, replacement_resource_id=replacement_id, reason=reason)
        self.db.add(record)
        self.db.flush()
        return {"product_id": product.id, "product_name": product.product_name, "old_quantity": old_quantity, "new_quantity": product.sale_quantity, "old_price": old_price, "new_price": product.suggested_price, "action": action, "bottleneck_resource": product.bottleneck_resource, "status": product.status, "replacement_resource_id": replacement_id, "reason": reason}
