from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ...core.exceptions import AppError
from ...db import get_db
from ...models import Merchant, PartnerResource, ProductResource, ResourceChangeEvent, TravelProduct, User
from ...schemas.resources import MediaImportRequest, MediaSearchRequest, PartnerResourceCreate, PartnerResourceRead, PartnerResourceUpdate
from ...services.product_service import ProductService
from ...services.serializers import partner_resource_to_dict
from ...services.media_library_service import MAX_MEDIA_BYTES, MediaLibraryService
from ..deps import get_merchant_user
from ..websocket_manager import manager

router = APIRouter(prefix="/merchant", tags=["merchant"])


def merchant_for(db: Session, user: User) -> Merchant:
    merchant = db.scalar(select(Merchant).where(Merchant.user_id == user.id))
    if not merchant:
        raise AppError("MERCHANT_NOT_FOUND", "当前账号未绑定合作商户", status_code=404)
    return merchant


@router.post("/media/upload")
async def upload_media(file: UploadFile = File(...), user: User = Depends(get_merchant_user)):
    _ = user
    content = await file.read(MAX_MEDIA_BYTES + 1)
    if len(content) > MAX_MEDIA_BYTES:
        raise AppError("MEDIA_CONTENT_INVALID", "图片不能超过 12MB。", field="file")
    return MediaLibraryService().store_upload(content, file.content_type)


@router.post("/media/search")
def search_media(request: MediaSearchRequest, user: User = Depends(get_merchant_user)):
    _ = user
    return {"items": MediaLibraryService().search_public(request.query, request.limit)}


@router.post("/media/import")
def import_media(request: MediaImportRequest, user: User = Depends(get_merchant_user)):
    _ = user
    return MediaLibraryService().import_remote(request.url, source=request.source, attribution=request.attribution)


def snapshot(resource: PartnerResource) -> dict:
    return {
        "id": resource.id,
        "resource_name": resource.resource_name,
        "remaining_capacity": resource.remaining_capacity,
        "settlement_price": str(resource.settlement_price),
        "market_price": str(resource.market_price),
        "package_enabled": resource.package_enabled,
        "status": resource.status,
        "available_date": resource.available_date.isoformat(),
        "start_time": resource.start_time.isoformat() if resource.start_time else None,
        "end_time": resource.end_time.isoformat() if resource.end_time else None,
    }


def normalized_status(resource: PartnerResource, requested: str | None) -> str:
    if requested in {"SUSPENDED", "UNAVAILABLE", "EXPIRED", "DRAFT"}:
        return requested
    if resource.remaining_capacity <= 0:
        return "SOLD_OUT"
    return "AVAILABLE"


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_merchant_user)):
    merchant = merchant_for(db, user)
    resources = list(db.scalars(select(PartnerResource).where(PartnerResource.merchant_id == merchant.id).order_by(PartnerResource.available_date, PartnerResource.id)).all())
    references = db.scalar(select(func.count(ProductResource.id)).join(TravelProduct, TravelProduct.id == ProductResource.product_id).where(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id.in_([item.id for item in resources]))) if resources else 0
    changes = list(db.scalars(select(ResourceChangeEvent).where(ResourceChangeEvent.resource_type == "PARTNER_RESOURCE", ResourceChangeEvent.resource_id.in_([item.id for item in resources])).order_by(ResourceChangeEvent.created_at.desc()).limit(6)).all()) if resources else []
    return {"merchant": {"id": merchant.id, "name": merchant.merchant_name, "category": merchant.category, "cooperation_status": merchant.cooperation_status}, "resource_count": len(resources), "available_capacity": sum(max(0, item.remaining_capacity) for item in resources if item.status == "AVAILABLE"), "package_references": int(references or 0), "low_stock_resources": sum(1 for item in resources if 0 < item.remaining_capacity <= 5), "recent_changes": [{"id": item.id, "reason": item.reason, "created_at": item.created_at, "processed": item.processed} for item in changes]}


@router.get("/resources", response_model=list[PartnerResourceRead])
def resources(db: Session = Depends(get_db), user: User = Depends(get_merchant_user)):
    merchant = merchant_for(db, user)
    items = list(db.scalars(select(PartnerResource).options(selectinload(PartnerResource.merchant)).where(PartnerResource.merchant_id == merchant.id).order_by(PartnerResource.available_date, PartnerResource.id)).all())
    return [partner_resource_to_dict(item, int(db.scalar(select(func.count(ProductResource.id)).where(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id == item.id)) or 0)) for item in items]


@router.post("/resources", response_model=PartnerResourceRead)
def create_resource(request: PartnerResourceCreate, db: Session = Depends(get_db), user: User = Depends(get_merchant_user)):
    merchant = merchant_for(db, user)
    resource = PartnerResource(merchant_id=merchant.id, **request.model_dump(), status=normalized_status(PartnerResource(remaining_capacity=request.remaining_capacity), None))
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return partner_resource_to_dict(resource)


@router.patch("/resources/{resource_id}", response_model=None)
async def update_resource(resource_id: int, request: PartnerResourceUpdate, db: Session = Depends(get_db), user: User = Depends(get_merchant_user)):
    merchant = merchant_for(db, user)
    resource = db.scalar(select(PartnerResource).options(selectinload(PartnerResource.merchant)).where(PartnerResource.id == resource_id, PartnerResource.merchant_id == merchant.id).with_for_update())
    if not resource:
        raise AppError("NOT_FOUND", "文旅资源不存在", status_code=404)
    old = snapshot(resource)
    data = request.model_dump(exclude_unset=True, exclude={"reason"})
    for key, value in data.items():
        setattr(resource, key, value)
    if resource.remaining_capacity < 0:
        raise AppError("VALIDATION_ERROR", "剩余名额不能为负数", field="remaining_capacity")
    if resource.start_time and resource.end_time and resource.start_time >= resource.end_time:
        raise AppError("TIME_INVALID", "活动开始时间必须早于结束时间")
    if resource.minimum_age is not None and resource.maximum_age is not None and resource.maximum_age < resource.minimum_age:
        raise AppError("AGE_INVALID", "最大适龄年龄不能小于最小适龄年龄")
    resource.status = normalized_status(resource, request.status)
    changed_keys = set(data)
    if "remaining_capacity" in changed_keys:
        event_type = "PARTNER_CAPACITY_CHANGED"
    elif "settlement_price" in changed_keys or "market_price" in changed_keys:
        event_type = "PARTNER_PRICE_CHANGED"
    else:
        event_type = "PARTNER_RESOURCE_STATUS_CHANGED"
    event = ResourceChangeEvent(event_type=event_type, resource_type="PARTNER_RESOURCE", resource_id=resource.id, hotel_id=merchant.hotel_id, old_value=old, new_value=snapshot(resource), reason=request.reason, operator_role=user.role, operator_id=user.id)
    db.add(event)
    db.flush()
    affected = ProductService(db, merchant.hotel_id).recalculate_for_event(event)
    db.commit()
    await manager.broadcast(merchant.hotel_id, {"type": "RESOURCE_CHANGE", "title": "合作资源发生变化", "message": f"{resource.resource_name}剩余名额已从{old['remaining_capacity']}调整为{resource.remaining_capacity}", "affectedProducts": affected})
    db.refresh(resource)
    return {"resource": partner_resource_to_dict(resource, int(db.scalar(select(func.count(ProductResource.id)).where(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id == resource.id)) or 0)), "event_id": event.id, "affected_products": affected, "message": "资源更新成功，受影响产品已完成重算"}


@router.get("/resources/{resource_id}/references")
def resource_references(resource_id: int, db: Session = Depends(get_db), user: User = Depends(get_merchant_user)):
    merchant = merchant_for(db, user)
    resource = db.scalar(select(PartnerResource).where(PartnerResource.id == resource_id, PartnerResource.merchant_id == merchant.id))
    if not resource:
        raise AppError("NOT_FOUND", "文旅资源不存在", status_code=404)
    products = list(db.scalars(select(TravelProduct).join(ProductResource).where(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id == resource_id).order_by(TravelProduct.updated_at.desc())).unique().all())
    return [{"product_id": item.id, "product_name": item.product_name, "sale_quantity": item.sale_quantity, "status": item.status, "suggested_price": item.suggested_price} for item in products]


@router.get("/changes")
def changes(db: Session = Depends(get_db), user: User = Depends(get_merchant_user)):
    merchant = merchant_for(db, user)
    resource_ids = [item.id for item in db.scalars(select(PartnerResource).where(PartnerResource.merchant_id == merchant.id)).all()]
    if not resource_ids:
        return []
    items = list(db.scalars(select(ResourceChangeEvent).where(ResourceChangeEvent.resource_type == "PARTNER_RESOURCE", ResourceChangeEvent.resource_id.in_(resource_ids)).order_by(ResourceChangeEvent.created_at.desc()).limit(100)).all())
    return items
