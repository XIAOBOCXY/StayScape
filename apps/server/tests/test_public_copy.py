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
