"""Transactional inventory primitives shared by publishing, holds and recalc.

The product quantity is a sellable projection.  Room, hotel-service and
partner-resource quantities remain the physical source of truth.  Keeping the
reservation snapshot on the visitor intent makes a hold reversible and keeps
the demo database honest after repeated runs.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..core.exceptions import AppError
from ..models import (
    HotelService,
    Merchant,
    PartnerResource,
    ProductAdjustmentRecord,
    ProductResource,
    ResourceChangeEvent,
    RoomInventory,
    TravelProduct,
    VisitorIntent,
)
from ..rules.availability_rule import resource_is_usable


ACTIVE_PRODUCT_STATUSES = {"ON_SALE", "LOW_STOCK"}


def _created_sort_key(value: datetime | None) -> float:
    """Normalize SQLite's naive datetime values before comparing rows."""
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _requirements(product: TravelProduct) -> dict[tuple[str, int], int]:
    requirements: dict[tuple[str, int], int] = defaultdict(int)
    requirements[("ROOM", product.room_inventory_id)] += 1
    for row in product.resources:
        if row.resource_type in {"HOTEL_SERVICE", "PARTNER_RESOURCE"}:
            requirements[(row.resource_type, row.resource_id)] += max(1, int(row.quantity_per_package))
    return dict(requirements)


def _source(db: Session, product: TravelProduct, resource_type: str, resource_id: int):
    if resource_type == "ROOM":
        return db.scalar(
            select(RoomInventory)
            .where(RoomInventory.id == resource_id, RoomInventory.hotel_id == product.hotel_id)
            .with_for_update()
        )
    if resource_type == "HOTEL_SERVICE":
        return db.scalar(
            select(HotelService)
            .where(HotelService.id == resource_id, HotelService.hotel_id == product.hotel_id)
            .with_for_update()
        )
    if resource_type == "PARTNER_RESOURCE":
        return db.scalar(
            select(PartnerResource)
            .join(Merchant)
            .where(PartnerResource.id == resource_id, Merchant.hotel_id == product.hotel_id)
            .with_for_update()
        )
    return None


def _source_available(source: Any) -> int:
    if isinstance(source, RoomInventory):
        return max(0, int(source.available_count))
    if isinstance(source, HotelService):
        return max(0, int(source.available_quantity))
    if isinstance(source, PartnerResource):
        return max(0, int(source.remaining_capacity))
    return 0


def _set_source_available(source: Any, value: int) -> None:
    if isinstance(source, RoomInventory):
        source.available_count = value
    elif isinstance(source, HotelService):
        source.available_quantity = value
    elif isinstance(source, PartnerResource):
        source.remaining_capacity = value


def _source_name(source: Any) -> str:
    return getattr(source, "room_type", None) or getattr(source, "service_name", None) or getattr(source, "resource_name", None) or "资源"


def _restore_availability_status(source: Any, quantity: int) -> None:
    if quantity <= 0:
        source.status = "SOLD_OUT"
    elif getattr(source, "status", None) == "SOLD_OUT":
        source.status = "AVAILABLE"


def _validate_source(product: TravelProduct, resource_type: str, source: Any) -> None:
    if source is None:
        raise AppError("INVENTORY_SOURCE_NOT_FOUND", "套餐依赖的库存资源不存在", retryable=True)
    if resource_type == "ROOM":
        if source.available_date != product.target_date or source.status in {"DISABLED", "SOLD_OUT"}:
            raise AppError("ROOM_INVENTORY_INSUFFICIENT", f"客房{_source_name(source)}当前不可占用", retryable=True)
    elif resource_type == "HOTEL_SERVICE":
        if source.available_date != product.target_date or source.status != "AVAILABLE":
            raise AppError("HOTEL_SERVICE_UNAVAILABLE", f"酒店服务{_source_name(source)}当前不可占用", retryable=True)
    elif resource_type == "PARTNER_RESOURCE":
        merchant = source.merchant
        if source.available_date != product.target_date or not resource_is_usable(
            merchant_status=merchant.cooperation_status if merchant else "TERMINATED",
            package_enabled=source.package_enabled,
            resource_status=source.status,
            capacity=source.remaining_capacity,
            source_type=source.source_type,
        ):
            raise AppError("PARTNER_RESOURCE_UNAVAILABLE", f"合作资源{_source_name(source)}当前不可占用", retryable=True)


def reserve_product_inventory(db: Session, product: TravelProduct) -> dict[str, Any]:
    """Atomically reserve one package from every physical source."""

    requirements = _requirements(product)
    loaded: list[tuple[str, int, int, Any]] = []
    for (resource_type, resource_id), quantity in requirements.items():
        source = _source(db, product, resource_type, resource_id)
        _validate_source(product, resource_type, source)
        available = _source_available(source)
        if available < quantity:
            raise AppError(
                "INVENTORY_INSUFFICIENT",
                f"{_source_name(source)}仅剩{available}，本套餐需要{quantity}",
                retryable=True,
                details={"resource_type": resource_type, "resource_id": resource_id, "available": available, "required": quantity},
            )
        loaded.append((resource_type, resource_id, quantity, source))

    allocations = []
    for resource_type, resource_id, quantity, source in loaded:
        before = _source_available(source)
        after = before - quantity
        _set_source_available(source, after)
        _restore_availability_status(source, after)
        allocations.append(
            {
                "resource_type": resource_type,
                "resource_id": resource_id,
                "resource_name": _source_name(source),
                "quantity": quantity,
                "before": before,
                "after": after,
            }
        )
    return {"allocations": allocations, "created_at": datetime.now(timezone.utc).isoformat()}


def _set_product_quantity_status(product: TravelProduct, quantity: int, preferred_status: str | None = None) -> None:
    product.sale_quantity = max(0, int(quantity))
    if product.sale_quantity <= 0:
        product.status = "SOLD_OUT" if preferred_status in ACTIVE_PRODUCT_STATUSES or preferred_status == "SOLD_OUT" else (preferred_status or product.status)
    elif preferred_status in ACTIVE_PRODUCT_STATUSES or product.status in ACTIVE_PRODUCT_STATUSES or product.status == "SOLD_OUT":
        product.status = "LOW_STOCK" if product.sale_quantity <= 2 else "ON_SALE"


def release_intent_inventory(db: Session, intent: VisitorIntent) -> dict[str, Any]:
    """Release a held intent exactly once and return the affected product."""

    if intent.reservation_status not in {"HELD", "CONFIRMED"}:
        return {"released": False, "product_id": intent.product_id, "reason": "reservation_not_held"}
    product = db.scalar(
        select(TravelProduct)
        .options(selectinload(TravelProduct.resources))
        .where(TravelProduct.id == intent.product_id)
        .with_for_update()
    )
    snapshot = intent.allocation_snapshot or {}
    allocations = snapshot.get("allocations", []) if isinstance(snapshot, dict) else []
    restored = []
    if product:
        for allocation in allocations:
            source = _source(db, product, allocation["resource_type"], int(allocation["resource_id"]))
            if source is None:
                continue
            before = _source_available(source)
            after = before + int(allocation.get("quantity", 0))
            _set_source_available(source, after)
            _restore_availability_status(source, after)
            restored.append({**allocation, "before": before, "after": after})
        before_product = product.sale_quantity
        _set_product_quantity_status(product, before_product + 1, snapshot.get("product_status_before"))
        snapshot["restored_allocations"] = restored
        snapshot["released_at"] = datetime.now(timezone.utc).isoformat()
        intent.allocation_snapshot = snapshot
    intent.reservation_status = "RELEASED"
    intent.intent_status = "CANCELLED" if intent.intent_status != "EXPIRED" else "EXPIRED"
    intent.released_at = datetime.now(timezone.utc)
    return {"released": True, "product_id": intent.product_id, "new_quantity": product.sale_quantity if product else None, "restored": restored}


def sweep_expired_intents(db: Session, hotel_id: int | None = None) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    query = select(VisitorIntent).where(VisitorIntent.reservation_status == "HELD", VisitorIntent.reserved_until.is_not(None), VisitorIntent.reserved_until <= now)
    if hotel_id is not None:
        query = query.join(TravelProduct).where(TravelProduct.hotel_id == hotel_id)
    intents = list(db.scalars(query.with_for_update()).all())
    released = []
    affected_hotels: set[int] = set()
    for intent in intents:
        result = release_intent_inventory(db, intent)
        intent.intent_status = "EXPIRED"
        intent.reservation_status = "EXPIRED"
        released.append(result)
        if intent.product:
            affected_hotels.add(intent.product.hotel_id)
    for affected_hotel_id in affected_hotels:
        reconcile_published_capacity(db, affected_hotel_id)
    return released


def _physical_capacity(db: Session, product: TravelProduct) -> dict[tuple[str, int], int]:
    capacities: dict[tuple[str, int], int] = {}
    for key in _requirements(product):
        source = _source(db, product, key[0], key[1])
        capacities[key] = _source_available(source) if source else 0
    return capacities


def _used_by_product(used: dict[tuple[str, int], int], product: TravelProduct, quantity: int) -> None:
    for key, per_package in _requirements(product).items():
        used[key] += per_package * max(0, quantity)


def reconcile_published_capacity(db: Session, hotel_id: int, *, priority_product_id: int | None = None, event: ResourceChangeEvent | None = None) -> list[dict[str, Any]]:
    """Cap concurrently published products so their sum never exceeds sources."""

    products = list(
        db.scalars(
            select(TravelProduct)
            .options(selectinload(TravelProduct.resources), selectinload(TravelProduct.adjustments))
            .where(TravelProduct.hotel_id == hotel_id, TravelProduct.status.in_(ACTIVE_PRODUCT_STATUSES))
            .order_by(TravelProduct.created_at, TravelProduct.id)
        ).unique().all()
    )
    if priority_product_id is not None:
        products.sort(key=lambda item: (0 if item.id == priority_product_id else 1, _created_sort_key(item.created_at), item.id))
    used: dict[tuple[str, int], int] = defaultdict(int)
    adjustments = []
    for product in products:
        old_quantity = product.sale_quantity
        old_price = product.suggested_price
        capacities = _physical_capacity(db, product)
        # Never use the already-reduced live quantity as the next target.  A
        # temporary hold would otherwise shrink it forever after cancellation.
        # ``listed_quantity`` is the merchant's ceiling; the source rows are
        # the live truth below it.
        listed = max(0, int(product.listed_quantity or 0))
        if not listed and old_quantity > 0:
            # Compatibility for records created before migration 0009.
            listed = old_quantity
            product.listed_quantity = listed
        cap = listed
        for key, per_package in _requirements(product).items():
            remaining = max(0, capacities.get(key, 0) - used[key])
            cap = min(cap, remaining // max(1, per_package))
        if cap != old_quantity:
            _set_product_quantity_status(product, cap, product.status)
            action = "SHARED_CAPACITY_GUARD" if cap else "PAUSE_SHARED_CAPACITY"
            record = ProductAdjustmentRecord(
                product_id=product.id,
                change_event_id=event.id if event else None,
                old_quantity=old_quantity,
                new_quantity=product.sale_quantity,
                old_price=old_price,
                new_price=product.suggested_price,
                action=action,
                reason="多个在售套餐共享底层库存，系统按真实容量自动分配可售数量",
            )
            db.add(record)
            adjustments.append({"product_id": product.id, "old_quantity": old_quantity, "new_quantity": product.sale_quantity, "status": product.status, "action": action})
        _used_by_product(used, product, product.sale_quantity)
    return adjustments


def ensure_publish_capacity(db: Session, product: TravelProduct) -> list[dict[str, Any]]:
    """Validate and cap a draft before it becomes visible to visitors."""

    reconcile_published_capacity(db, product.hotel_id)
    active = list(
        db.scalars(
            select(TravelProduct)
            .options(selectinload(TravelProduct.resources))
            .where(TravelProduct.hotel_id == product.hotel_id, TravelProduct.status.in_(ACTIVE_PRODUCT_STATUSES), TravelProduct.id != product.id)
        ).unique().all()
    )
    used: dict[tuple[str, int], int] = defaultdict(int)
    for other in active:
        _used_by_product(used, other, other.sale_quantity)
    capacities = _physical_capacity(db, product)
    if product.listed_quantity <= 0:
        product.listed_quantity = max(0, product.sale_quantity)
    cap = product.listed_quantity
    for key, per_package in _requirements(product).items():
        cap = min(cap, max(0, capacities.get(key, 0) - used[key]) // max(1, per_package))
    if cap <= 0:
        raise AppError("CAPACITY_INSUFFICIENT", "该套餐与其他在售套餐共享的底层库存已不足，无法发布", field="status", retryable=True)
    if cap < product.sale_quantity:
        _set_product_quantity_status(product, cap, "ON_SALE")
    return reconcile_published_capacity(db, product.hotel_id, priority_product_id=product.id)
