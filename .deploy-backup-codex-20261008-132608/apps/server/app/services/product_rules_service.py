"""Canonical product business rules used by generation, editing and publishing.

This service is deliberately small and deterministic.  It owns the two rules
that used to be reimplemented in ProductRefiner and the publish-check path:
the legal price floor and the current sellable quantity.  AI services may
explain these values, but never calculate them independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import HotelService, PartnerResource, RoomInventory, TravelProduct, VisitorIntent
from ..rules.capacity_rule import CapacityInput, CapacityResult, calculate_sale_quantity
from ..rules.pricing_rule import calculate_pricing

ROOM = "ROOM"
PARTNER_RESOURCE = "PARTNER_RESOURCE"
HOTEL_SERVICE = "HOTEL_SERVICE"


@dataclass(frozen=True)
class ResourceCapacity:
    """One capacity constraint on a product, with enough detail to explain it."""

    name: str
    kind: str
    resource_id: int
    capacity: int
    available: bool
    remaining: int = 0
    quantity_per_package: int = 1
    date_hint: str = ""
    indoor: bool = True


class ProductRulesService:
    def __init__(self, db: Session, hotel_id: int) -> None:
        self.db = db
        self.hotel_id = hotel_id

    def committed_rooms(self, room: RoomInventory) -> int:
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

    def price_floor(self, product: TravelProduct) -> Decimal:
        room = self.db.get(RoomInventory, product.room_inventory_id)
        experience_notes = getattr(product, "experience_notes", None) or {}
        extra_room_ids = experience_notes.get("stay_room_inventory_ids", []) if isinstance(experience_notes, dict) else []
        extra_rooms = [self.db.get(RoomInventory, int(room_id)) for room_id in extra_room_ids if str(room_id).isdigit()]
        room_minimum = sum(
            (Decimal(str(item.minimum_price or 0)) for item in ([room] if room is not None else []) + [item for item in extra_rooms if item is not None]),
            Decimal("0"),
        )
        result = calculate_pricing(
            unit_cost=Decimal(str(product.unit_cost or 0)),
            room_minimum_price=room_minimum,
            minimum_gross_margin=Decimal(str(product.minimum_gross_margin_requirement or "0.2")),
        )
        return result.minimum_allowed_price

    def capacity_breakdown(self, product: TravelProduct, *, require_available: bool = False) -> list[ResourceCapacity]:
        """Every capacity constraint that limits how many packages can be sold.

        ``require_available`` is the difference between "how many could this
        composition support" (false, used while editing) and "how many may we
        publish right now" (true, used before publishing).  A resource row that
        cannot be resolved at all is reported as capacity 0 so a broken product
        never looks sellable.
        """

        rows: list[ResourceCapacity] = []
        room = self.db.get(RoomInventory, product.room_inventory_id)
        if room is not None:
            available = str(room.status) == "AVAILABLE"
            pool = max(0, int(room.available_count or 0) - self.committed_rooms(room))
            rows.append(
                ResourceCapacity(
                    name=room.room_type,
                    kind=ROOM,
                    resource_id=int(room.id),
                    capacity=pool if available or not require_available else 0,
                    available=available,
                    remaining=pool,
                    date_hint=str(room.available_date or ""),
                )
            )
        else:
            rows.append(ResourceCapacity(name="客房", kind=ROOM, resource_id=0, capacity=0, available=False))
        experience_notes = getattr(product, "experience_notes", None) or {}
        extra_room_ids = experience_notes.get("stay_room_inventory_ids", []) if isinstance(experience_notes, dict) else []
        valid_extra_room_ids = [room_id for room_id in extra_room_ids if str(room_id).isdigit()]
        for offset, room_id in enumerate(valid_extra_room_ids, start=1):
            if not str(room_id).isdigit() or (room is not None and int(room_id) == int(room.id)):
                continue
            extra_room = self.db.get(RoomInventory, int(room_id))
            expected_date = product.target_date + timedelta(days=offset)
            if (
                extra_room is None
                or int(extra_room.hotel_id) != int(product.hotel_id)
                or extra_room.room_type != (room.room_type if room is not None else extra_room.room_type)
                or extra_room.available_date != expected_date
            ):
                rows.append(ResourceCapacity(name="住宿房态", kind=ROOM, resource_id=int(room_id), capacity=0, available=False))
                continue
            available = str(extra_room.status) == "AVAILABLE"
            remaining = max(0, int(extra_room.available_count or 0))
            rows.append(
                ResourceCapacity(
                    name=f"{extra_room.room_type} · {extra_room.available_date}",
                    kind=ROOM,
                    resource_id=int(extra_room.id),
                    capacity=remaining if available or not require_available else 0,
                    available=available,
                    remaining=remaining,
                    date_hint=str(extra_room.available_date or ""),
                )
            )
        expected_extra_nights = max(0, int(product.nights or 1) - 1)
        if len(valid_extra_room_ids) < expected_extra_nights:
            for offset in range(len(valid_extra_room_ids) + 1, expected_extra_nights + 1):
                rows.append(
                    ResourceCapacity(
                        name=f"第{offset + 1}晚住宿房态缺失",
                        kind=ROOM,
                        resource_id=0,
                        capacity=0,
                        available=False,
                        date_hint=str(product.target_date + timedelta(days=offset)),
                    )
                )
        for row in product.resources:
            quantity = max(1, int(row.quantity_per_package or 1))
            if row.resource_type == "PARTNER_RESOURCE":
                resource = self.db.get(PartnerResource, row.resource_id)
                if resource is None:
                    rows.append(ResourceCapacity(name=row.resource_name, kind=PARTNER_RESOURCE, resource_id=int(row.resource_id or 0), capacity=0, available=False))
                    continue
                available = str(resource.status) == "AVAILABLE" and bool(resource.package_enabled)
                capacity = int(resource.remaining_capacity or 0) // quantity
                rows.append(
                    ResourceCapacity(
                        name=resource.resource_name,
                        kind=PARTNER_RESOURCE,
                        resource_id=int(resource.id),
                        capacity=capacity if available or not require_available else 0,
                        available=available,
                        remaining=int(resource.remaining_capacity or 0),
                        quantity_per_package=quantity,
                        indoor=bool(getattr(resource, "indoor", False)),
                    )
                )
            elif row.resource_type == "HOTEL_SERVICE":
                service = self.db.get(HotelService, row.resource_id)
                if service is None:
                    rows.append(ResourceCapacity(name=row.resource_name, kind=HOTEL_SERVICE, resource_id=int(row.resource_id or 0), capacity=0, available=False))
                    continue
                available = str(service.status) == "AVAILABLE"
                capacity = int(service.available_quantity or 0) // quantity
                rows.append(
                    ResourceCapacity(
                        name=service.service_name,
                        kind=HOTEL_SERVICE,
                        resource_id=int(service.id),
                        capacity=capacity if available or not require_available else 0,
                        available=available,
                        remaining=int(service.available_quantity or 0),
                        quantity_per_package=quantity,
                    )
                )
        return rows

    def sale_quantity(self, product: TravelProduct, *, require_available: bool = False) -> CapacityResult:
        rows = self.capacity_breakdown(product, require_available=require_available)
        if not rows:
            # The shared capacity rule treats an empty input list as a caller
            # error; answer 0 explicitly instead of raising from edit paths.
            return CapacityResult(sale_quantity=0, bottleneck_resource=None, supported_quantities={})
        return calculate_sale_quantity([CapacityInput(row.name, row.capacity, 1) for row in rows])
