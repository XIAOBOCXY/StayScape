"""Idempotently add dated demo inventory for late-October StayScape demos.

Run with: docker compose cp scripts/seed_late_october_demo_inventory.py server:/tmp/seed_late_october_demo_inventory.py
          docker compose exec -T server python /tmp/seed_late_october_demo_inventory.py
All copied partner inventory is marked DEMO; this does not assert real-world availability.
"""
from __future__ import annotations
import argparse
import json
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any
from sqlalchemy import and_, or_, select
from app.db import SessionLocal
from app.models import HotelService, Merchant, PartnerResource, ProductResource, RoomInventory
from app.models.entities import User

DEMO_USERNAME = "hotel_demo"
TEMPLATE_START = date(2026, 10, 6)
TEMPLATE_END = date(2026, 10, 15)
TARGET_START = date(2026, 10, 16)
# Covers the checkout day of a four-day itinerary starting on October 31.
TARGET_END = date(2026, 11, 3)


def template_date(target: date) -> date:
    matches = [TEMPLATE_START + timedelta(days=i) for i in range((TEMPLATE_END - TEMPLATE_START).days + 1)
               if (TEMPLATE_START + timedelta(days=i)).weekday() == target.weekday()]
    if not matches:
        raise RuntimeError(f"No weekday template for {target.isoformat()}")
    return matches[-1]


def clone(model: type[Any], source: Any, target: date, *, demo_partner: bool = False) -> Any:
    values = {column.name: getattr(source, column.name) for column in model.__table__.columns
              if column.name not in {"id", "created_at", "updated_at"}}
    values["available_date"] = target
    if demo_partner:
        values["source_type"] = "DEMO"
    return model(**values)


def is_dining(resource: PartnerResource) -> bool:
    text = f"{resource.category or ''} {resource.resource_name or ''}".upper()
    if any(word in text for word in ("手作", "制作", "陶艺", "课堂", "烘焙", "工作坊")):
        return False
    return any(word in text for word in ("DINING", "RESTAURANT", "餐饮", "餐厅", "用餐", "午餐", "晚餐", "杭帮菜", "美食", "FOOD"))


def missing_coverage(rows: list[PartnerResource]) -> list[str]:
    rows = [row for row in rows if row.status == "AVAILABLE" and row.package_enabled and row.remaining_capacity > 0]
    meal = any(is_dining(row) and row.start_time and (
        690 <= row.start_time.hour * 60 + row.start_time.minute < 810
        or 1020 <= row.start_time.hour * 60 + row.start_time.minute < 1200
    ) for row in rows)
    morning = any(not is_dining(row) and row.start_time and row.end_time
        and row.start_time.hour * 60 + row.start_time.minute < 690
        and row.end_time.hour * 60 + row.end_time.minute > 480 for row in rows)
    afternoon = any(not is_dining(row) and row.start_time and row.end_time
        and row.start_time.hour * 60 + row.start_time.minute < 1050
        and row.end_time.hour * 60 + row.end_time.minute > 810 for row in rows)
    paid = any(not is_dining(row) and row.market_price is not None and row.market_price > 0 for row in rows)
    return [label for label, ok in (("午餐或晚餐", meal), ("上午体验", morning), ("下午体验", afternoon), ("付费体验", paid)) if not ok]


def seed(session, manifest_path: Path) -> dict[str, Any]:
    user = session.scalar(select(User).where(User.username == DEMO_USERNAME))
    if user is None or user.hotel_id is None:
        raise RuntimeError(f"Demo account {DEMO_USERNAME!r} has no hotel")
    hotel_id = user.hotel_id
    inserted = {"rooms": [], "hotel_services": [], "partner_resources": []}
    target = TARGET_START
    while target <= TARGET_END:
        template = template_date(target)
        room_templates = list(session.scalars(select(RoomInventory).where(
            RoomInventory.hotel_id == hotel_id, RoomInventory.available_date == template,
            RoomInventory.status == "AVAILABLE", RoomInventory.available_count > 0)))
        service_templates = list(session.scalars(select(HotelService).where(
            HotelService.hotel_id == hotel_id, HotelService.available_date == template,
            HotelService.status == "AVAILABLE", HotelService.available_quantity > 0)))
        partner_templates = list(session.scalars(select(PartnerResource).join(Merchant).where(
            Merchant.hotel_id == hotel_id, Merchant.cooperation_status == "ACTIVE",
            PartnerResource.available_date == template, PartnerResource.source_type.in_(("PARTNER", "DEMO")),
            PartnerResource.status == "AVAILABLE", PartnerResource.package_enabled.is_(True),
            PartnerResource.remaining_capacity > 0)).unique())
        if not room_templates or not service_templates or not partner_templates:
            raise RuntimeError(f"{template.isoformat()} is missing a complete demo template")

        room_types = set(session.scalars(select(RoomInventory.room_type).where(
            RoomInventory.hotel_id == hotel_id, RoomInventory.available_date == target)))
        for source in room_templates:
            if source.room_type in room_types:
                continue
            item = clone(RoomInventory, source, target)
            session.add(item)
            session.flush()
            inserted["rooms"].append(item.id)
            room_types.add(source.room_type)

        service_keys = set(session.execute(select(HotelService.service_type, HotelService.service_name).where(
            HotelService.hotel_id == hotel_id, HotelService.available_date == target)).all())
        for source in service_templates:
            key = (source.service_type, source.service_name)
            if key in service_keys:
                continue
            item = clone(HotelService, source, target)
            session.add(item)
            session.flush()
            inserted["hotel_services"].append(item.id)
            service_keys.add(key)

        partner_keys = set(session.execute(select(
            PartnerResource.merchant_id, PartnerResource.resource_name,
            PartnerResource.category, PartnerResource.start_time, PartnerResource.end_time,
        ).join(Merchant).where(
            Merchant.hotel_id == hotel_id, PartnerResource.available_date == target,
            PartnerResource.source_type.in_(("PARTNER", "DEMO")))).all())
        day_rows = list(session.scalars(select(PartnerResource).join(Merchant).where(
            Merchant.hotel_id == hotel_id, PartnerResource.available_date == target,
            PartnerResource.source_type.in_(("PARTNER", "DEMO")), PartnerResource.status == "AVAILABLE",
            PartnerResource.package_enabled.is_(True), PartnerResource.remaining_capacity > 0)).unique())
        for source in partner_templates:
            key = (source.merchant_id, source.resource_name, source.category, source.start_time, source.end_time)
            if key in partner_keys:
                continue
            item = clone(PartnerResource, source, target, demo_partner=True)
            session.add(item)
            session.flush()
            inserted["partner_resources"].append(item.id)
            partner_keys.add(key)
            day_rows.append(item)

        # Add two clearly demo-sourced lunch sessions so 3-4 day itineraries
        # can use distinct dining experiences on each day without repeating.
        for source_name, demo_name in (
            ("杭帮菜双人体验", "仁和路杭帮菜午餐体验"),
            ("湖滨夜市美食漫游", "湖滨风味午餐体验"),
        ):
            if any(row.resource_name == demo_name for row in day_rows):
                continue
            source = next((row for row in day_rows if row.resource_name == source_name), None)
            if source is None:
                raise RuntimeError(f"{target.isoformat()} has no source for demo meal {demo_name}")
            item = clone(PartnerResource, source, target, demo_partner=True)
            item.resource_name = demo_name
            item.start_time = time(12, 0)
            item.end_time = time(13, 0)
            item.description = f"{source.description}（演示午餐场次）"
            session.add(item)
            session.flush()
            inserted["partner_resources"].append(item.id)
            day_rows.append(item)

        missing = missing_coverage(day_rows)
        if missing:
            raise RuntimeError(f"{target.isoformat()} lacks demo coverage: {', '.join(missing)}")
        target += timedelta(days=1)

    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous_inserted = previous.get("inserted", {})
        for key in inserted:
            inserted[key] = list(dict.fromkeys(previous_inserted.get(key, []) + inserted[key]))

    manifest = {"hotel_id": hotel_id, "target_start": TARGET_START.isoformat(),
        "target_end": TARGET_END.isoformat(), "inserted": inserted,
        "counts": {key: len(ids) for key, ids in inserted.items()}}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def rollback(session, manifest_path: Path) -> dict[str, int]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inserted = manifest["inserted"]
    rooms, services, partners = (set(inserted[key]) for key in ("rooms", "hotel_services", "partner_resources"))
    clauses = []
    if rooms:
        clauses.append(and_(ProductResource.resource_type == "ROOM", ProductResource.resource_id.in_(rooms)))
    if services:
        clauses.append(and_(ProductResource.resource_type == "HOTEL_SERVICE", ProductResource.resource_id.in_(services)))
    if partners:
        clauses.append(and_(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id.in_(partners)))
    if clauses and session.scalar(select(ProductResource.id).where(or_(*clauses)).limit(1)) is not None:
        raise RuntimeError("Seeded rows are used by a product; remove that product before rollback")
    for model, ids in ((PartnerResource, partners), (HotelService, services), (RoomInventory, rooms)):
        if ids:
            for item in session.scalars(select(model).where(model.id.in_(ids))):
                session.delete(item)
    return {key: len(inserted[key]) for key in inserted}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("/tmp/stayscape-demo-inventory-manifest.json"))
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    with SessionLocal.begin() as session:
        result = rollback(session, args.manifest) if args.rollback else seed(session, args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
