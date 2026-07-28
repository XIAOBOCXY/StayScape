from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ...core.exceptions import AppError
from ...db import get_db
from ...models import Hotel, HotelService, Merchant, PartnerResource, ProductResource, ResourceChangeEvent, RoomInventory, SkillCallLog, TravelProduct, User, VisitorIntent
from ...repositories.product_repository import get_product, list_products
from ...repositories.resource_repository import list_partner_resources, list_rooms, list_services
from ...schemas.dashboard import DashboardResponse
from ...schemas.products import AdjustmentRead, GenerateProductRequest, ProductDetailResponse, ProductGenerateResponse, ProductListResponse, ProductRead, ProductStatusRequest, ResourceChangeResponse
from ...schemas.resources import MerchantRead, PartnerResourceRead, RoomCreate, RoomRead, RoomUpdate, ServiceCreate, ServiceRead, ServiceUpdate
from ...services.product_service import ProductService
from ...services.serializers import partner_resource_to_dict, product_to_dict
from ..deps import get_hotel_user, resolve_hotel_id
from ..websocket_manager import manager

router = APIRouter(prefix="/hotel", tags=["hotel"])


def hotel_id_for(db: Session, user: User) -> int:
    return resolve_hotel_id(db, user)


def room_status(count: int, requested: str | None = None) -> str:
    if requested == "DISABLED":
        return "DISABLED"
    if count <= 0:
        return "SOLD_OUT"
    return "LOW_STOCK" if count <= 2 else "AVAILABLE"


def service_status(quantity: int, requested: str | None = None) -> str:
    if requested in {"UNAVAILABLE", "SUSPENDED", "EXPIRED"}:
        return requested
    return "SOLD_OUT" if quantity <= 0 else "AVAILABLE"


def room_snapshot(room: RoomInventory) -> dict:
    return {"id": room.id, "available_count": room.available_count, "status": room.status, "minimum_price": str(room.minimum_price), "normal_price": str(room.normal_price), "accounting_cost": str(room.accounting_cost)}


def service_snapshot(service: HotelService) -> dict:
    return {"id": service.id, "available_quantity": service.available_quantity, "status": service.status, "unit_cost": str(service.unit_cost), "reference_price": str(service.reference_price)}


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    hotel = db.get(Hotel, hotel_id)
    target = date.today() + __import__("datetime").timedelta(days=1)
    rooms = list_rooms(db, hotel_id)
    resources = list_partner_resources(db, hotel_id)
    products = list_products(db, hotel_id)
    intents = db.scalar(select(func.count(VisitorIntent.id)).join(TravelProduct).where(TravelProduct.hotel_id == hotel_id)) or 0
    changes = list(db.scalars(select(ResourceChangeEvent).order_by(ResourceChangeEvent.created_at.desc()).limit(6)).all())
    return {
        "hotel_id": hotel_id,
        "hotel_name": hotel.name if hotel else "StayScape",
        "target_date": target.isoformat(),
        "room_count": len(rooms),
        "expiring_room_count": sum(1 for item in rooms if item.available_date == target),
        "available_room_units": sum(max(0, item.available_count) for item in rooms if item.available_date == target),
        "partner_resource_count": len(resources),
        "package_enabled_resource_count": sum(1 for item in resources if item.package_enabled and item.status == "AVAILABLE"),
        "product_count": len(products),
        "on_sale_product_count": sum(1 for item in products if item.status == "ON_SALE"),
        "low_stock_product_count": sum(1 for item in products if item.status == "LOW_STOCK"),
        "visitor_intent_count": int(intents),
        "gross_profit_on_sale": sum((item.gross_profit * item.sale_quantity for item in products if item.status in {"ON_SALE", "LOW_STOCK"}), Decimal("0")),
        "recent_changes": [{"id": item.id, "event_type": item.event_type, "resource_type": item.resource_type, "resource_id": item.resource_id, "reason": item.reason, "processed": item.processed, "created_at": item.created_at} for item in changes],
    }


@router.get("/rooms", response_model=list[RoomRead])
def rooms(db: Session = Depends(get_db), user: User = Depends(get_hotel_user), target_date: date | None = Query(default=None)):
    hotel_id = hotel_id_for(db, user)
    items = list_rooms(db, hotel_id)
    return [item for item in items if target_date is None or item.available_date == target_date]


@router.post("/rooms", response_model=RoomRead)
def create_room(request: RoomCreate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    if request.minimum_price > request.normal_price:
        raise AppError("VALIDATION_ERROR", "最低售价不能高于正常售价", field="minimum_price")
    hotel_id = hotel_id_for(db, user)
    item = RoomInventory(hotel_id=hotel_id, **request.model_dump(), status=room_status(request.available_count))
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/rooms/{room_id}", response_model=RoomRead)
async def update_room(room_id: int, request: RoomUpdate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    room = db.scalar(select(RoomInventory).where(RoomInventory.id == room_id, RoomInventory.hotel_id == hotel_id).with_for_update())
    if not room:
        raise AppError("NOT_FOUND", "客房库存不存在", status_code=404)
    old = room_snapshot(room)
    data = request.model_dump(exclude_unset=True, exclude={"reason"})
    for key, value in data.items():
        setattr(room, key, value)
    if room.minimum_price > room.normal_price:
        raise AppError("VALIDATION_ERROR", "最低售价不能高于正常售价", field="minimum_price")
    if room.available_count < 0 or room.accounting_cost <= 0:
        raise AppError("VALIDATION_ERROR", "库存和核算成本必须合法")
    room.status = room_status(room.available_count, room.status)
    event = ResourceChangeEvent(event_type="ROOM_INVENTORY_CHANGED", resource_type="ROOM", resource_id=room.id, old_value=old, new_value=room_snapshot(room), reason=request.reason, operator_role=user.role, operator_id=user.id)
    db.add(event)
    db.flush()
    affected = ProductService(db, hotel_id).recalculate_for_event(event)
    db.commit()
    await manager.broadcast(hotel_id, {"type": "RESOURCE_CHANGE", "title": "临期客房发生变化", "message": request.reason, "affectedProducts": affected})
    db.refresh(room)
    return room


@router.get("/services", response_model=list[ServiceRead])
def services(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    return list_services(db, hotel_id_for(db, user))


@router.post("/services", response_model=ServiceRead)
def create_service(request: ServiceCreate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    if request.start_time and request.end_time and request.start_time >= request.end_time:
        raise AppError("TIME_INVALID", "服务开始时间必须早于结束时间")
    hotel_id = hotel_id_for(db, user)
    item = HotelService(hotel_id=hotel_id, **request.model_dump(), status=service_status(request.available_quantity))
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/services/{service_id}", response_model=ServiceRead)
async def update_service(service_id: int, request: ServiceUpdate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    service = db.scalar(select(HotelService).where(HotelService.id == service_id, HotelService.hotel_id == hotel_id).with_for_update())
    if not service:
        raise AppError("NOT_FOUND", "酒店服务不存在", status_code=404)
    old = service_snapshot(service)
    data = request.model_dump(exclude_unset=True, exclude={"reason"})
    for key, value in data.items():
        setattr(service, key, value)
    if service.available_quantity < 0:
        raise AppError("VALIDATION_ERROR", "服务名额不能为负数", field="available_quantity")
    if service.start_time and service.end_time and service.start_time >= service.end_time:
        raise AppError("TIME_INVALID", "服务开始时间必须早于结束时间")
    service.status = service_status(service.available_quantity, service.status)
    event_type = "HOTEL_SERVICE_STATUS_CHANGED" if old["status"] != service.status else "HOTEL_SERVICE_QUANTITY_CHANGED"
    event = ResourceChangeEvent(event_type=event_type, resource_type="HOTEL_SERVICE", resource_id=service.id, old_value=old, new_value=service_snapshot(service), reason=request.reason, operator_role=user.role, operator_id=user.id)
    db.add(event)
    db.flush()
    affected = ProductService(db, hotel_id).recalculate_for_event(event)
    db.commit()
    await manager.broadcast(hotel_id, {"type": "RESOURCE_CHANGE", "title": "酒店服务发生变化", "message": request.reason, "affectedProducts": affected})
    db.refresh(service)
    return service


@router.get("/merchants", response_model=list[MerchantRead])
def merchants(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    return list(db.scalars(select(Merchant).where(Merchant.hotel_id == hotel_id_for(db, user)).order_by(Merchant.id)).all())


@router.get("/resources", response_model=list[PartnerResourceRead])
def resources(db: Session = Depends(get_db), user: User = Depends(get_hotel_user), only_package_enabled: bool | None = None):
    hotel_id = hotel_id_for(db, user)
    items = list_partner_resources(db, hotel_id)
    result = []
    for item in items:
        if only_package_enabled is not None and item.package_enabled != only_package_enabled:
            continue
        count = db.scalar(select(func.count(ProductResource.id)).where(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id == item.id)) or 0
        result.append(partner_resource_to_dict(item, int(count)))
    return result


@router.patch("/resources/{resource_id}/package", response_model=PartnerResourceRead)
async def toggle_package(resource_id: int, package_enabled: bool, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    resource = db.scalar(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(PartnerResource.id == resource_id, Merchant.hotel_id == hotel_id).with_for_update())
    if not resource:
        raise AppError("NOT_FOUND", "合作资源不存在", status_code=404)
    old = {"package_enabled": resource.package_enabled, "status": resource.status}
    resource.package_enabled = package_enabled
    event = ResourceChangeEvent(event_type="PARTNER_RESOURCE_STATUS_CHANGED", resource_type="PARTNER_RESOURCE", resource_id=resource.id, old_value=old, new_value={"package_enabled": resource.package_enabled, "status": resource.status}, reason="酒店调整组包许可", operator_role=user.role, operator_id=user.id)
    db.add(event)
    db.flush()
    affected = ProductService(db, hotel_id).recalculate_for_event(event)
    db.commit()
    await manager.broadcast(hotel_id, {"type": "RESOURCE_CHANGE", "title": "合作资源组包许可发生变化", "message": "酒店调整了资源组包许可", "affectedProducts": affected})
    db.refresh(resource)
    count = db.scalar(select(func.count(ProductResource.id)).where(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id == resource.id)) or 0
    return partner_resource_to_dict(resource, int(count))


@router.get("/products", response_model=ProductListResponse)
def products(db: Session = Depends(get_db), user: User = Depends(get_hotel_user), status: str | None = None):
    items = list_products(db, hotel_id_for(db, user))
    if status:
        items = [item for item in items if item.status == status]
    return {"items": [product_to_dict(item) for item in items], "total": len(items)}


@router.post("/products/generate", response_model=ProductGenerateResponse)
def generate_product(request: GenerateProductRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    product, validation, trace_id, fallback_used = ProductService(db, hotel_id_for(db, user)).generate(request)
    db.commit()
    return {"product": product_to_dict(product), "trace_id": trace_id, "validation": validation, "fallback_used": fallback_used}


@router.get("/products/{product_id}", response_model=ProductDetailResponse)
def product_detail(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id_for(db, user):
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    return product_to_dict(product, include_adjustments=True)


@router.patch("/products/{product_id}/status", response_model=ProductRead)
def product_status(product_id: int, request: ProductStatusRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id_for(db, user):
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    if request.status == "ON_SALE" and product.sale_quantity <= 0:
        raise AppError("CAPACITY_INSUFFICIENT", "库存为0的产品不能发布", field="status")
    product.status = request.status
    db.commit()
    return product_to_dict(product)


@router.get("/products/{product_id}/adjustments", response_model=list[AdjustmentRead])
def product_adjustments(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id_for(db, user):
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    return product.adjustments


@router.get("/changes")
def changes(db: Session = Depends(get_db), user: User = Depends(get_hotel_user), limit: int = Query(default=50, ge=1, le=200)):
    hotel_id = hotel_id_for(db, user)
    resource_ids = [item.id for item in list_partner_resources(db, hotel_id)]
    items = list(db.scalars(select(ResourceChangeEvent).where(or_(ResourceChangeEvent.resource_type.in_(["ROOM", "HOTEL_SERVICE"]), (ResourceChangeEvent.resource_type == "PARTNER_RESOURCE") & ResourceChangeEvent.resource_id.in_(resource_ids))).order_by(ResourceChangeEvent.created_at.desc()).limit(limit)).all())
    return [{"id": item.id, "event_type": item.event_type, "resource_type": item.resource_type, "resource_id": item.resource_id, "old_value": item.old_value, "new_value": item.new_value, "reason": item.reason, "processed": item.processed, "processing_result": item.processing_result, "created_at": item.created_at} for item in items]


@router.get("/intents")
def intents(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    items = list(db.scalars(select(VisitorIntent).join(TravelProduct).where(TravelProduct.hotel_id == hotel_id).order_by(VisitorIntent.created_at.desc())).all())
    return [{"id": item.id, "product_id": item.product_id, "adult_count": item.adult_count, "child_count": item.child_count, "child_ages": item.child_ages, "budget": item.budget, "interests": item.interests, "dietary_restrictions": item.dietary_restrictions, "allergy_information": item.allergy_information, "arrival_time": item.arrival_time, "preferred_experience_time": item.preferred_experience_time, "intent_status": item.intent_status, "contact_name": item.contact_name, "contact_phone": item.contact_phone, "created_at": item.created_at} for item in items]


@router.get("/skill-logs")
def skill_logs(db: Session = Depends(get_db), user: User = Depends(get_hotel_user), limit: int = Query(default=50, ge=1, le=200)):
    items = list(db.scalars(select(SkillCallLog).order_by(SkillCallLog.created_at.desc()).limit(limit)).all())
    return items

