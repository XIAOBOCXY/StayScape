from app.services.public_copy import public_travel_copy


def test_public_copy_replaces_internal_operational_sentence():
    fallback = "住进杭州，慢慢体验这座城市的另一面。"
    value = "每一套都包含住宿、酒店服务和一段真实可用的文化体验。库存变化会同步到这里。"
    assert public_travel_copy(value, fallback) == fallback


def test_public_copy_keeps_travel_facing_sentence():
    value = "从良渚看展到湘湖散步，把一段想去的杭州留给周末。"
    assert public_travel_copy(value, "fallback") == value


def test_late_checkout_is_not_scheduled_on_arrival_day():
    from app.services.public_copy import build_day_plan

    resources = [
        {"resource_type": "ROOM", "resource_name": "亲子房"},
        {"resource_type": "HOTEL_SERVICE", "resource_name": "延迟退房", "start_time": "12:00:00", "end_time": "14:00:00"},
        {"resource_type": "PARTNER_RESOURCE", "resource_name": "儿童茶文化课堂", "start_time": "16:00:00", "end_time": "17:30:00"},
    ]
    stay = {"nights": 1, "check_in": "2026-09-30", "room_name": "亲子房", "label": "2天1晚"}
    days = build_day_plan(resources, stay)

    assert all(item["title"] != "延迟退房" for item in days[0]["items"])
    assert days[-1]["items"][-1]["title"] == "返回酒店取行李"


def test_three_hour_experience_excludes_overlapping_suggested_stops():
    from app.services.public_copy import build_day_plan

    day = build_day_plan(
        [{
            "resource_type": "PARTNER_RESOURCE",
            "resource_name": "良渚博物馆深度导览",
            "start_time": "11:00:00",
            "end_time": "14:00:00",
            "address": "杭州市余杭区良渚街道良渚博物院正门",
        }],
        {"nights": 1, "hotel_address": "杭州市余杭区良渚街道良渚博物院正门"},
    )[0]
    for item in day["items"]:
        if item.get("kind") != "PUBLIC_REFERENCE":
            continue
        assert item["time"] not in {"09:30–11:30", "13:30–15:00"}


def test_distinct_experiences_show_transfer_time_or_flag_tight_gap():
    from app.services.public_copy import build_day_plan

    resources = [
        {"resource_type": "PARTNER_RESOURCE", "resource_name": "茶文化体验", "start_time": "13:00:00", "end_time": "16:00:00", "address": "杭州市西湖区龙井村茶园入口"},
        {"resource_type": "PARTNER_RESOURCE", "resource_name": "手作体验", "start_time": "16:30:00", "end_time": "17:30:00", "address": "杭州市西湖区龙井路手作馆正门"},
    ]
    day = build_day_plan(resources, {"nights": 1, "hotel_address": "杭州市西湖区龙井村茶园入口"})[0]
    transfer = next(item for item in day["items"] if item.get("kind") == "TRANSFER")
    assert transfer["time"] == "16:05–16:30"
    assert transfer["duration_minutes"] == 25

    resources[1]["start_time"] = "16:10:00"
    day = build_day_plan(resources, {"nights": 1, "hotel_address": "杭州市西湖区龙井村茶园入口"})[0]
    next_experience = next(item for item in day["items"] if item["title"] == "手作体验")
    assert next_experience["schedule_conflict"] is True
    assert "至少建议预留 25 分钟" in next_experience["notes"]


def test_new_product_resource_selection_rejects_too_short_inter_area_transfer():
    from datetime import time
    from types import SimpleNamespace

    from app.services.product_service import _partner_transfer_issue

    resources = [
        SimpleNamespace(resource_name="茶文化体验", start_time=time(13, 0), end_time=time(16, 0), address="杭州市西湖区龙井村茶园入口"),
        SimpleNamespace(resource_name="手作体验", start_time=time(16, 10), end_time=time(17, 30), address="杭州市西湖区龙井路手作馆正门"),
    ]
    issue = _partner_transfer_issue(resources)
    assert issue is not None
    assert "至少预留 25 分钟转场" in issue


def test_evening_route_requires_confirmed_opening_through_the_slot():
    from datetime import date
    from app.services.public_copy import _evening_accessible

    assert not _evening_accessible({"name": "杭州博物馆", "category": "MUSEUM", "opening_hours": "09:00-17:00"})
    assert not _evening_accessible({"name": "浙江省博物馆", "category": "MUSEUM", "opening_hours": "请以官方公告为准"})
    assert not _evening_accessible({"name": "夜游运河", "category": "CRUISE", "opening_hours": "18:00-22:00", "verification_status": "VERIFY_REQUIRED"})
    assert _evening_accessible({"name": "夜游运河", "category": "CRUISE", "opening_hours": "18:00-22:00", "verification_status": "ACTIVE"})
    assert not _evening_accessible({"name": "全天开放园区", "category": "PARK", "opening_hours": "全天开放", "verification_status": "VERIFY_REQUIRED"})
    assert _evening_accessible({"name": "全天开放园区", "category": "PARK", "opening_hours": "全天开放", "verification_status": "ACTIVE"})
    monday = {"name": "城市博物馆", "category": "MUSEUM", "opening_hours": "09:00-21:00，周一闭馆", "verification_status": "ACTIVE"}
    assert not _evening_accessible(monday, visit_date=date(2026, 10, 5))
    assert _evening_accessible(monday, visit_date=date(2026, 10, 6))
