"""Idempotently seed varied Oct-Nov listings and historical confirmed sales for the demo hotel.

This script adds dated inventory only for the StayScape demo hotel. Historical confirmed rows are sample records so the operating charts and order history have dated examples; they do not consume current inventory.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Hotel, TravelProduct, User, VisitorIntent
from app.seed import DEMO_PASSWORD
from app.showcase_catalog import seed_extra_catalog
from app.showcase_seed import seed_showcase_products


FUTURE_END = date(2026, 11, 30)
HISTORY_TARGETS = [
    (6, 6), (6, 19), (6, 28),
    (7, 4), (7, 16), (7, 29),
    (8, 8), (8, 17), (8, 28),
    (9, 5), (9, 16), (9, 27),
    (10, 2), (10, 4), (10, 6), (10, 7),
]
DOUBLE_PRODUCT_DATES = {(6, 19), (7, 16), (8, 17), (9, 16)}
GUEST_NAMES = ["周女士", "陈先生", "林女士", "吴先生", "许女士", "沈先生", "顾女士", "郑先生", "叶女士", "何先生"]


def seed(db) -> dict[str, int]:
    # Seed only the hotel represented by the known demo operator account. Picking
    # the first hotel is unsafe on a multi-tenant production database.
    hotel_user = db.scalar(select(User).where(User.username == "hotel_demo", User.role == "HOTEL"))
    if hotel_user is None or hotel_user.hotel_id is None:
        raise RuntimeError("The hotel_demo operator account is missing or is not linked to a hotel; refusing to seed an ambiguous tenant.")
    hotel = db.get(Hotel, hotel_user.hotel_id)
    if hotel is None:
        raise RuntimeError("The hotel_demo operator account references a missing hotel; refusing to seed catalog data.")
    hotel_id = int(hotel.id)
    inserted_future_products = 0
    target = date(2026, 10, 9)
    offset = 0
    while target <= FUTURE_END:
        # Supply room and activity rows for the full stay window, so 3-day
        # packages and generated itineraries can use real inventory on each day.
        for stay_offset in range(4):
            seed_extra_catalog(
                db,
                hotel_id,
                target + timedelta(days=stay_offset),
                demo_password=DEMO_PASSWORD,
                variation=offset + stay_offset,
            )
        result = seed_showcase_products(db, hotel_id, target, variant_count=4)
        inserted_future_products += int(result.get("created", 0))
        target += timedelta(days=4)
        offset += 1

    inserted_history_products = 0
    inserted_orders = 0
    year = date.today().year
    existing_keys = set(db.scalars(select(VisitorIntent.client_request_id).where(
        VisitorIntent.client_request_id.like("history-sample-v1-%")
    )))
    for month, day in HISTORY_TARGETS:
        stay_date = date(year, month, day)
        if stay_date >= date.today():
            continue
        seed_extra_catalog(db, hotel_id, stay_date, demo_password=DEMO_PASSWORD, variation=month * 7 + day)
        result = seed_showcase_products(
            db, hotel_id, stay_date,
            variant_count=2 if (month, day) in DOUBLE_PRODUCT_DATES else 1,
        )
        inserted_history_products += int(result.get("created", 0))
        products = list(db.scalars(select(TravelProduct).where(
            TravelProduct.hotel_id == hotel_id,
            TravelProduct.target_date == stay_date,
            TravelProduct.product_code.like("SC-%"),
        ).order_by(TravelProduct.id)))
        # Past packages remain linked to their confirmed order history, but
        # must not look purchasable after their travel date has passed.
        for product in products:
            product.status = "EXPIRED"
        # One sale per product keeps the sample history varied and avoids
        # suggesting that a past transaction consumed today's room/resource stock.
        order_slots = 2 if (month, day) in DOUBLE_PRODUCT_DATES else 1
        created_at = datetime.combine(stay_date - timedelta(days=3), time(10, 0), tzinfo=timezone.utc)
        for slot, product in enumerate(products[:order_slots]):
            key = f"history-sample-v1-{stay_date.isoformat()}-{slot + 1}"
            if key in existing_keys:
                continue
            family = str(product.target_crowd or "") == "FAMILY"
            adults = max(1, int(product.party_size or 2) - (1 if family else 0))
            children = 1 if family and int(product.party_size or 0) > 1 else 0
            guest_index = (month * 3 + day + slot) % len(GUEST_NAMES)
            db.add(VisitorIntent(
                product_id=product.id,
                natural_language=f"想在{month}月来杭州体验{product.theme}，同行{product.party_size}人。",
                adult_count=adults,
                child_count=children,
                child_ages=[7] if children else [],
                budget=Decimal(product.suggested_price),
                interests=[str(product.theme), str(product.target_crowd)],
                negative_interests=[],
                activity_level="MEDIUM",
                dietary_restrictions=[],
                allergy_information="",
                other_requirements="",
                recommendation_result={"source": "historical_catalog_seed", "product_theme": str(product.theme)},
                intent_status="CONFIRMED",
                reservation_status="CONFIRMED",
                reserved_until=None,
                allocation_snapshot={"historical_sample": True, "consumes_current_stock": False},
                released_at=None,
                confirmed_at=created_at,
                contact_name=GUEST_NAMES[guest_index],
                contact_phone=f"138001380{guest_index:02d}",
                client_request_id=key,
                created_at=created_at,
                updated_at=created_at,
            ))
            existing_keys.add(key)
            inserted_orders += 1
    db.commit()
    return {"future_products_added": inserted_future_products, "historical_products_added": inserted_history_products, "historical_confirmed_orders_added": inserted_orders}


def main() -> None:
    db = SessionLocal()
    try:
        print(seed(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
