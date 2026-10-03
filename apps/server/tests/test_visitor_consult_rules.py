from datetime import date
from types import SimpleNamespace

from app.api.v1 import visitor
from app.schemas.visitor import VisitorRecommendRequest


def test_explicit_calendar_date_accepts_iso_and_chinese_month_day():
    assert visitor.explicit_calendar_date("改成 2026-10-08") == date(2026, 10, 8)
    assert visitor.explicit_calendar_date("改到10月8号", date(2026, 9, 30)) == date(2026, 10, 8)
    assert visitor.explicit_calendar_date("原来是10月3号，改成10月8号", date(2026, 9, 30)) == date(2026, 10, 8)
    assert visitor.explicit_calendar_date("改到2月30日", date(2026, 1, 1)) is None


def test_missing_child_age_does_not_reject_every_age_restricted_product(monkeypatch):
    resource = SimpleNamespace(
        weather_tags="RAIN,SUNNY,CLOUDY",
        suitable_crowds="ALL",
        minimum_age=6,
        maximum_age=12,
        resource_name="亲子手作",
        address="杭州西湖区",
        description="室内文化体验",
        category="CULTURE",
    )
    monkeypatch.setattr(visitor, "product_partner_rows", lambda _db, _product: [(None, resource)])
    product = SimpleNamespace(
        room_inventory_id=1,
        product_name="亲子手作套餐",
        theme="亲子文化",
        marketing_content="室内手作体验",
        target_crowd="ALL",
        suggested_price=500,
    )
    request = VisitorRecommendRequest(adult_count=2, child_count=1, child_ages=[], weather="UNKNOWN")
    db = SimpleNamespace(get=lambda *_args: SimpleNamespace(max_guests=4))

    children_match, weather_match, *_ = visitor.matches_conditions(db, product, request)

    assert children_match is True
    assert weather_match is True


def test_public_stop_uses_verified_full_duration_or_stays_unscheduled(monkeypatch):
    from app.services import public_copy

    place = {
        "name": "城市博物馆",
        "category": "MUSEUM",
        "address": "杭州市上城区",
        "description": "馆藏展览",
        "opening_hours": "09:00–17:00",
        "suggested_duration_minutes": 180,
        "verification_status": "ACTIVE",
        "source_name": "博物馆官网",
        "source_url": "https://museum.example.cn/visit",
    }
    monkeypatch.setattr(public_copy, "_public_route_places", lambda *_args: [place])

    day = public_copy.build_day_plan([], {"nights": 1, "check_in": "2026-10-08", "hotel_address": "杭州市上城区"})[0]

    assert not any(item.get("kind") == "PUBLIC_REFERENCE" for item in day["items"])
