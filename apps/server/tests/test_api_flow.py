from app.config import settings
from app.agent.mock_agent import MockAgent


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def generate_request(client, token):
    rooms = client.get("/api/v1/hotel/rooms", headers=auth(token)).json()
    services = client.get("/api/v1/hotel/services", headers=auth(token)).json()
    resources = client.get("/api/v1/hotel/resources", headers=auth(token)).json()
    target_date = rooms[0]["available_date"]
    room = next(item for item in rooms if item["room_type"] == "亲子房")
    breakfast = next(item for item in services if item["service_type"] == "BREAKFAST")
    late = next(item for item in services if item["service_type"] == "LATE_CHECKOUT")
    craft = next(item for item in resources if "非遗" in item["resource_name"])
    request = {
        "target_date": target_date,
        "weather": "RAIN",
        "target_crowd": "FAMILY",
        "minimum_gross_margin": "0.20",
        "visitor_budget": "700",
        "theme": "雨天亲子非遗",
        "room_inventory_id": room["id"],
        "resource_selections": [
            {"resource_type": "HOTEL_SERVICE", "resource_id": breakfast["id"], "quantity_per_package": 3},
            {"resource_type": "HOTEL_SERVICE", "resource_id": late["id"], "quantity_per_package": 1},
            {"resource_type": "PARTNER_RESOURCE", "resource_id": craft["id"], "quantity_per_package": 3},
        ],
        "preferred_price": "599",
    }
    return request, craft


def test_login_and_core_product_generation(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    response = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    assert response.status_code == 200, response.text
    data = response.json()
    product = data["product"]
    assert product["product_name"] == "杭州雨天亲子非遗文化宿"
    assert product["sale_quantity"] == 4
    assert product["unit_cost"] == "455.00"
    assert product["suggested_price"] == "599.00"
    assert product["gross_profit"] == "144.00"
    assert 0.2403 < float(product["gross_margin"]) < 0.2405
    assert data["trace_id"].startswith("trace_")


def test_merchant_capacity_change_recalculates_product(client, hotel_token, merchant_token):
    request, craft = generate_request(client, hotel_token)
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    assert generated.status_code == 200, generated.text
    product_id = generated.json()["product"]["id"]
    published = client.patch(f"/api/v1/hotel/products/{product_id}/status", headers=auth(hotel_token), json={"status": "ON_SALE"})
    assert published.status_code == 200, published.text
    changed = client.patch(f"/api/v1/merchant/resources/{craft['id']}", headers=auth(merchant_token), json={"remaining_capacity": 4, "reason": "其他渠道已预约8人"})
    assert changed.status_code == 200, changed.text
    affected = changed.json()["affected_products"]
    assert affected and affected[0]["old_quantity"] == 4 and affected[0]["new_quantity"] == 1
    products = client.get("/api/v1/hotel/products", headers=auth(hotel_token)).json()["items"]
    product = next(item for item in products if item["id"] == product_id)
    assert product["sale_quantity"] == 1
    assert product["status"] == "LOW_STOCK"
    assert product["bottleneck_resource"] == "室内非遗手作体验"


def test_visitor_recommendation_and_intent(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    product = generated.json()["product"]
    client.patch(f"/api/v1/hotel/products/{product['id']}/status", headers=auth(hotel_token), json={"status": "ON_SALE"})
    recommendation = client.post("/api/v1/visitor/recommend", json={"target_date": request["target_date"], "weather": "RAIN", "adult_count": 2, "child_count": 1, "child_ages": [6], "budget": "700", "interests": ["手工"], "allergy_information": "花生过敏", "arrival_time": "15:00", "preferred_experience_time": "16:00"})
    assert recommendation.status_code == 200, recommendation.text
    data = recommendation.json()
    assert data["results"]
    assert data["results"][0]["product"]["id"] == product["id"]
    assert "过敏" in data["results"][0]["allergy_warning"]
    assert any(item["id"] == product["id"] for item in client.get("/api/v1/visitor/products").json())
    intent = client.post("/api/v1/visitor/intents", json={"product_id": product["id"], "natural_language": "一家三口带一个6岁孩子，下午四点体验，孩子花生过敏。", "adult_count": 2, "child_count": 1, "child_ages": [6], "budget": "700", "interests": ["手工"], "allergy_information": "花生过敏", "contact_name": "张三", "contact_phone": "13800138000"})
    assert intent.status_code == 200, intent.text
    assert intent.json()["contact_phone_masked"] == "138****8000"
    assert intent.json()["remaining_quantity"] == 3
    public_product = next(item for item in client.get("/api/v1/visitor/products").json() if item["id"] == product["id"])
    assert public_product["sale_quantity"] == 3
    hotel_intent = client.get("/api/v1/hotel/intents", headers=auth(hotel_token)).json()[0]
    assert hotel_intent["product_name"] == product["product_name"]
    assert hotel_intent["contact_name"] == "张三"
    assert "花生过敏" in hotel_intent["other_requirements"]
    assert hotel_intent["remaining_quantity"] == 3


def test_agent_format_repair_is_logged(client, hotel_token):
    old_mode = settings.mock_agent_mode
    settings.mock_agent_mode = "invalid_once"
    try:
        request, _ = generate_request(client, hotel_token)
        response = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
        assert response.status_code == 200, response.text
        logs = client.get("/api/v1/hotel/skill-logs", headers=auth(hotel_token)).json()
        assert logs[0]["call_status"] == "SUCCESS"
        assert logs[0]["retry_count"] == 1
        assert logs[0]["validation_result"]["repaired"] is True
    finally:
        settings.mock_agent_mode = old_mode


def test_partner_suspension_replaces_then_pauses_when_no_candidate(client, hotel_token, merchant_token):
    request, craft = generate_request(client, hotel_token)
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    product_id = generated.json()["product"]["id"]
    client.patch(f"/api/v1/hotel/products/{product_id}/status", headers=auth(hotel_token), json={"status": "ON_SALE"})
    replaced = client.patch(f"/api/v1/merchant/resources/{craft['id']}", headers=auth(merchant_token), json={"status": "SUSPENDED", "reason": "原体验暂停，测试替代资源"})
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["affected_products"][0]["action"] == "REPLACE_RESOURCE"
    product = client.get(f"/api/v1/hotel/products/{product_id}", headers=auth(hotel_token)).json()
    assert any(item["resource_name"] == "儿童茶文化课堂" for item in product["resources"])


def test_agent_timeout_uses_fallback_without_breaking_business(client, hotel_token):
    old_mode = settings.mock_agent_mode
    settings.mock_agent_mode = "timeout"
    try:
        request, _ = generate_request(client, hotel_token)
        response = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
        assert response.status_code == 200, response.text
        assert response.json()["fallback_used"] is True
        logs = client.get("/api/v1/hotel/skill-logs", headers=auth(hotel_token)).json()
        assert logs[0]["call_status"] == "FALLBACK"
        assert logs[0]["error_code"] == "AGENT_TIMEOUT"
    finally:
        settings.mock_agent_mode = old_mode


def test_role_boundaries_are_enforced(client, hotel_token, merchant_token):
    assert client.get("/api/v1/hotel/dashboard").status_code == 401
    assert client.get("/api/v1/hotel/services", headers=auth(merchant_token)).status_code == 403
    assert client.get("/api/v1/merchant/resources", headers=auth(hotel_token)).status_code == 403
    assert client.get("/api/v1/visitor/products").status_code == 200


def test_merchant_can_create_and_edit_resource_name_date_and_session(client, hotel_token, merchant_token):
    target_date = client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json()[0]["available_date"]
    created = client.post("/api/v1/merchant/resources", headers=auth(merchant_token), json={
        "resource_name": "西溪湿地亲子手作",
        "category": "CULTURE",
        "description": "面向家庭的城市文化体验",
        "available_date": target_date,
        "start_time": "14:00",
        "end_time": "15:30",
        "remaining_capacity": 8,
        "settlement_price": "50",
        "market_price": "88",
        "suitable_crowds": "FAMILY",
        "minimum_age": 5,
        "maximum_age": 60,
        "indoor": True,
        "weather_tags": "RAIN,SUNNY",
        "package_enabled": True,
    })
    assert created.status_code == 200, created.text
    resource_id = created.json()["id"]
    updated = client.patch(f"/api/v1/merchant/resources/{resource_id}", headers=auth(merchant_token), json={"resource_name": "西溪湿地雨天手作", "available_date": target_date, "start_time": "15:00", "end_time": "16:30", "reason": "更新场次"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["resource"]["resource_name"] == "西溪湿地雨天手作"
    assert updated.json()["resource"]["start_time"].startswith("15:00")


def test_multi_variant_generation_and_marketing_assets(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    request["variant_count"] = 3
    request["creative_direction"] = "偏亲子研学"
    response = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    assert response.status_code == 200, response.text
    products = response.json()["products"]
    assert len(products) == 3
    assert len({item["product_name"] for item in products}) == 3
    assert {item["sale_quantity"] for item in products} == {4}
    assert {asset["asset_type"] for asset in products[0]["marketing_assets"]} >= {"POSTER", "SOCIAL_POST", "SHORT_VIDEO_SCRIPT"}


def test_product_content_update_and_delete(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    product_id = generated.json()["product"]["id"]
    updated = client.patch(f"/api/v1/hotel/products/{product_id}", headers=auth(hotel_token), json={"weather": "SUNNY", "theme": "晴日亲子茶文化", "regenerate_marketing": True})
    assert updated.status_code == 200, updated.text
    assert updated.json()["weather"] == "SUNNY"
    assert updated.json()["marketing_assets"]
    deleted = client.delete(f"/api/v1/hotel/products/{product_id}", headers=auth(hotel_token))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True
    assert all(item["id"] != product_id for item in client.get("/api/v1/hotel/products", headers=auth(hotel_token)).json()["items"])


def test_natural_language_recommendation_is_interpreted_before_matching(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    product_id = generated.json()["product"]["id"]
    client.patch(f"/api/v1/hotel/products/{product_id}/status", headers=auth(hotel_token), json={"status": "ON_SALE"})
    recommendation = client.post("/api/v1/visitor/recommend", json={"target_date": request["target_date"], "natural_language": "一家三口带一个6岁孩子，预算700元，明天下雨，喜欢非遗手工，孩子花生过敏。"})
    assert recommendation.status_code == 200, recommendation.text
    interpreted = recommendation.json()["interpreted_needs"]
    assert interpreted["weather"] == "RAIN"
    assert interpreted["child_ages"] == [6]
    assert "花生" in interpreted["allergy_information"]
    assert recommendation.json()["results"]


def test_hotel_can_toggle_package_permission_with_explicit_body_value(client, hotel_token):
    resources = client.get("/api/v1/hotel/resources", headers=auth(hotel_token)).json()
    resource = next(item for item in resources if "非遗" in item["resource_name"])
    disabled = client.patch(f"/api/v1/hotel/resources/{resource['id']}/package", headers=auth(hotel_token), json={"package_enabled": False})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["package_enabled"] is False
    enabled = client.patch(f"/api/v1/hotel/resources/{resource['id']}/package", headers=auth(hotel_token), json={"package_enabled": True})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["package_enabled"] is True


def test_hotel_can_create_and_edit_expiring_room_date(client, hotel_token):
    rooms = client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json()
    target_date = rooms[0]["available_date"]
    created = client.post("/api/v1/hotel/rooms", headers=auth(hotel_token), json={
        "room_type": "景观亲子房",
        "available_date": target_date,
        "available_count": 2,
        "normal_price": "699",
        "minimum_price": "499",
        "accounting_cost": "280",
        "max_guests": 4,
        "features": "落地窗、儿童用品",
    })
    assert created.status_code == 200, created.text
    room_id = created.json()["id"]
    updated = client.patch(f"/api/v1/hotel/rooms/{room_id}", headers=auth(hotel_token), json={"available_date": "2099-12-30", "available_count": 5, "reason": "调整临期日期"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["available_date"] == "2099-12-30"
    assert updated.json()["available_count"] == 5


def test_alternative_partner_variants_do_not_conflict_with_each_other(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    resources = client.get("/api/v1/hotel/resources", headers=auth(hotel_token)).json()
    tea = next(item for item in resources if item["resource_name"] == "儿童茶文化课堂")
    request["resource_selections"].append({"resource_type": "PARTNER_RESOURCE", "resource_id": tea["id"], "quantity_per_package": 3})
    request["variant_count"] = 2
    response = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    assert response.status_code == 200, response.text
    products = response.json()["products"]
    assert len(products) == 2
    partner_names = [next(item["resource_name"] for item in item["resources"] if item["resource_type"] == "PARTNER_RESOURCE") for item in products]
    assert set(partner_names) == {"室内非遗手作体验", "儿童茶文化课堂"}


def test_automatic_variants_use_one_compatible_session_instead_of_merging_overlaps(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    request["resource_selections"] = []
    request["variant_count"] = 3
    response = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    assert response.status_code == 200, response.text
    products = response.json()["products"]
    assert len(products) == 3
    assert all(sum(item["resource_type"] == "PARTNER_RESOURCE" for item in product["resources"]) == 1 for product in products)


def test_custom_multi_day_plan_holds_and_releases_real_inventory(client, hotel_token):
    dates = sorted({item["available_date"] for item in client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json()})
    assert len(dates) >= 2
    proposal = client.post(
        "/api/v1/visitor/trip-plans/propose",
        json={
            "natural_language": "两个人第一天看展吃饭，第二天去博物馆和西湖，不要太赶。",
            "start_date": dates[0],
            "duration_days": 2,
            "party_size": 2,
            "target_crowd": "COUPLE",
            "weather": "CLOUDY",
            "include_breakfast": True,
            "plan_name": "两天杭州看展行程",
        },
    )
    assert proposal.status_code == 200, proposal.text
    draft = proposal.json()["plans"][0]
    rooms = [item for item in draft["items"] if item["resource_type"] == "ROOM"]
    assert len(rooms) == 2
    second_day_experiences = [
        item["resource_name"]
        for item in draft["itinerary"]
        if item["resource_type"] == "PARTNER_RESOURCE" and item["day"] == 2
    ]
    assert any("博物馆" in name for name in second_day_experiences)
    before = {item["id"]: item["available_count"] for item in client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json()}
    held = client.post(
        "/api/v1/visitor/trip-plans/hold",
        json={
            "natural_language": "两个人第一天看展吃饭，第二天去博物馆和西湖，不要太赶。",
            "start_date": dates[0],
            "duration_days": 2,
            "party_size": 2,
            "target_crowd": "COUPLE",
            "weather": "CLOUDY",
            "include_breakfast": True,
            "plan_name": "两天杭州看展行程",
            "items": draft["items"],
            "contact_name": "王五",
            "contact_phone": "13600136000",
        },
    )
    assert held.status_code == 200, held.text
    assert held.json()["status"] == "HELD"
    after_hold = {item["id"]: item["available_count"] for item in client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json()}
    assert all(after_hold[item["resource_id"]] == before[item["resource_id"]] - 1 for item in rooms)
    released = client.post(f"/api/v1/visitor/trip-plans/{held.json()['id']}/cancel", json={"contact_phone": "13600136000"})
    assert released.status_code == 200, released.text
    after_release = {item["id"]: item["available_count"] for item in client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json()}
    assert all(after_release[item["resource_id"]] == before[item["resource_id"]] for item in rooms)


def test_natural_language_interpretation_returns_confirmable_requirement_card(client):
    response = client.post("/api/v1/visitor/interpret", json={"natural_language": "两大两小，孩子6岁和9岁，周六去西湖和运河，预算1000元，花生过敏，不吃辣"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["interpreted_needs"]["adult_count"] == 2
    assert data["interpreted_needs"]["child_ages"] == [6, 9]
    assert "西湖" in data["interpreted_needs"]["requested_places"]
    assert "花生" in data["interpreted_needs"]["allergy_information"]


def test_intent_reserves_and_cancellation_releases_physical_inventory(client, hotel_token):
    request, craft = generate_request(client, hotel_token)
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    product = generated.json()["product"]
    client.patch(f"/api/v1/hotel/products/{product['id']}/status", headers=auth(hotel_token), json={"status": "ON_SALE"})
    rooms_before = client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json()
    services_before = client.get("/api/v1/hotel/services", headers=auth(hotel_token)).json()
    resources_before = client.get("/api/v1/hotel/resources", headers=auth(hotel_token)).json()
    room = next(item for item in rooms_before if item["id"] == request["room_inventory_id"])
    breakfast = next(item for item in services_before if item["service_type"] == "BREAKFAST")
    late = next(item for item in services_before if item["service_type"] == "LATE_CHECKOUT")
    partner = next(item for item in resources_before if item["id"] == craft["id"])
    intent = client.post("/api/v1/visitor/intents", json={"product_id": product["id"], "adult_count": 2, "child_count": 1, "child_ages": [6], "budget": "700", "interests": ["手工"], "contact_name": "李四", "contact_phone": "13900139000"})
    assert intent.status_code == 200, intent.text
    assert intent.json()["reservation_status"] == "HELD"
    assert next(item for item in client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json() if item["id"] == room["id"])["available_count"] == room["available_count"] - 1
    assert next(item for item in client.get("/api/v1/hotel/services", headers=auth(hotel_token)).json() if item["id"] == breakfast["id"])["available_quantity"] == breakfast["available_quantity"] - 3
    assert next(item for item in client.get("/api/v1/hotel/services", headers=auth(hotel_token)).json() if item["id"] == late["id"])["available_quantity"] == late["available_quantity"] - 1
    assert next(item for item in client.get("/api/v1/hotel/resources", headers=auth(hotel_token)).json() if item["id"] == partner["id"])["remaining_capacity"] == partner["remaining_capacity"] - 3
    cancelled = client.post(f"/api/v1/visitor/intents/{intent.json()['id']}/cancel", json={"contact_phone": "13900139000"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["reservation_status"] == "RELEASED"
    assert next(item for item in client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json() if item["id"] == room["id"])["available_count"] == room["available_count"]
    assert next(item for item in client.get("/api/v1/hotel/resources", headers=auth(hotel_token)).json() if item["id"] == partner["id"])["remaining_capacity"] == partner["remaining_capacity"]


def test_recalculation_uses_original_margin_policy(client, hotel_token, merchant_token):
    request, craft = generate_request(client, hotel_token)
    request["minimum_gross_margin"] = "0.30"
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    assert generated.status_code == 200, generated.text
    product = generated.json()["product"]
    assert float(product["minimum_gross_margin_requirement"]) == 0.30
    changed = client.patch(f"/api/v1/merchant/resources/{craft['id']}", headers=auth(merchant_token), json={"remaining_capacity": 4, "reason": "验证原始毛利策略"})
    assert changed.status_code == 200, changed.text
    refreshed = client.get(f"/api/v1/hotel/products/{product['id']}", headers=auth(hotel_token)).json()
    assert refreshed["sale_quantity"] == 1
    assert refreshed["minimum_allowed_price"] == "650.00"
    assert float(refreshed["gross_margin"]) >= 0.30


def test_publishing_shared_candidates_cannot_overcommit_source_inventory(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    request["variant_count"] = 2
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    assert generated.status_code == 200, generated.text
    products = generated.json()["products"]
    first = client.patch(f"/api/v1/hotel/products/{products[0]['id']}/status", headers=auth(hotel_token), json={"status": "ON_SALE"})
    assert first.status_code == 200, first.text
    second = client.patch(f"/api/v1/hotel/products/{products[1]['id']}/status", headers=auth(hotel_token), json={"status": "ON_SALE"})
    assert second.status_code == 400, second.text
    assert second.json()["error"]["code"] == "CAPACITY_INSUFFICIENT"


def test_recommendation_enforces_room_capacity_arrival_and_score_ceiling(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    product = generated.json()["product"]
    client.patch(f"/api/v1/hotel/products/{product['id']}/status", headers=auth(hotel_token), json={"status": "ON_SALE"})
    over_capacity = client.post("/api/v1/visitor/recommend", json={"target_date": request["target_date"], "weather": "RAIN", "adult_count": 3, "child_count": 1, "child_ages": [6], "budget": "700", "interests": ["手工"]})
    assert over_capacity.status_code == 200 and over_capacity.json()["results"] == []
    too_late = client.post("/api/v1/visitor/recommend", json={"target_date": request["target_date"], "weather": "RAIN", "adult_count": 2, "child_count": 1, "child_ages": [6], "budget": "700", "interests": ["手工"], "arrival_time": "17:00"})
    assert too_late.status_code == 200 and too_late.json()["results"] == []
    valid = client.post("/api/v1/visitor/recommend", json={"target_date": request["target_date"], "weather": "RAIN", "adult_count": 2, "child_count": 1, "child_ages": [6], "budget": "700", "interests": ["手工"], "arrival_time": "15:00"})
    assert valid.status_code == 200 and valid.json()["results"]
    assert all(item["score"] <= 100 for item in valid.json()["results"])


def test_confirmed_intent_cancellation_releases_reserved_inventory(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    product = generated.json()["product"]
    client.patch(f"/api/v1/hotel/products/{product['id']}/status", headers=auth(hotel_token), json={"status": "ON_SALE"})
    room_before = next(item for item in client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json() if item["id"] == request["room_inventory_id"])
    intent = client.post("/api/v1/visitor/intents", json={"product_id": product["id"], "adult_count": 2, "child_count": 1, "child_ages": [6], "budget": "700", "contact_name": "Confirmed Guest", "contact_phone": "13700137000"})
    assert intent.status_code == 200, intent.text
    confirmed = client.patch(f"/api/v1/hotel/intents/{intent.json()['id']}", headers=auth(hotel_token), json={"status": "CONFIRMED"})
    assert confirmed.status_code == 200, confirmed.text
    dashboard = client.get("/api/v1/hotel/dashboard", headers=auth(hotel_token))
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["confirmed_order_count"] >= 1
    assert float(dashboard.json()["confirmed_revenue"]) >= float(product["suggested_price"])
    assert dashboard.json()["sales_timeline"]
    cancelled = client.post(f"/api/v1/visitor/intents/{intent.json()['id']}/cancel", json={"contact_phone": "13700137000"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["reservation_status"] == "RELEASED"
    room_after = next(item for item in client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json() if item["id"] == room_before["id"])
    assert room_after["available_count"] == room_before["available_count"]


def test_rich_catalog_covers_real_hangzhou_consumption_scenes(client, hotel_token):
    rooms = client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json()
    services = client.get("/api/v1/hotel/services", headers=auth(hotel_token)).json()
    resources = client.get("/api/v1/hotel/resources", headers=auth(hotel_token)).json()
    assert len(rooms) >= 9
    assert len(services) >= 20
    assert len(resources) >= 30
    assert {item["category"] for item in resources} >= {"CULTURE", "THEME_PARK", "SPORT", "NIGHTLIFE", "FOOD", "NATURE", "PERFORMANCE"}
    assert {item["source_type"] for item in resources} >= {"PARTNER", "DEMO", "PUBLIC_REFERENCE"}
    assert any(item["source_type"] == "PUBLIC_REFERENCE" and not item["package_enabled"] for item in resources)


def test_demo_seed_builds_a_multi_persona_public_product_pool(client, hotel_token):
    seeded = client.post("/api/v1/demo/seed", headers=auth(hotel_token))
    assert seeded.status_code == 200, seeded.text
    products = client.get("/api/v1/visitor/products").json()
    assert len(products) >= 12
    assert {item["target_crowd"] for item in products} >= {"FAMILY", "COUPLE", "FRIENDS", "SOLO", "LOCAL_WEEKEND"}
    assert {item["weather"] for item in products} >= {"RAIN", "SUNNY", "CLOUDY"}
    assert len({item["product_name"] for item in products}) >= 10


def test_mock_agent_uses_resource_category_for_creative_direction():
    agent = MockAgent()
    base = {
        "target_date": "2099-01-01",
        "weather": "RAIN",
        "target_crowd": "FRIENDS",
        "theme": "雨天运动娱乐",
        "preferred_price": "699",
        "room_inventory": {"id": 1, "room_type": "影音娱乐房", "features": "投影"},
        "requested_selections": [{"resource_type": "PARTNER_RESOURCE", "resource_id": 9, "quantity_per_package": 1}],
        "allowed_hotel_services": [],
        "allowed_partner_resources": [{"id": 9, "resource_name": "室内攀岩体验", "category": "SPORT", "description": "室内运动", "remaining_capacity": 12, "start_time": "16:00", "end_time": "17:30", "address": "运动馆", "settlement_price": "88", "indoor": True}],
    }
    output = agent._product(base)
    assert "运动" in output["product_name"] or "挑战" in output["product_name"]
    assert "攀岩" in output["marketing_content"]
    assert "SPORT" in output["marketing_assets"][0]["visual_brief"]


def test_natural_language_negative_preference_changes_persona_and_filters_category(client, hotel_token):
    seeded = client.post("/api/v1/demo/seed", headers=auth(hotel_token))
    assert seeded.status_code == 200, seeded.text
    response = client.post("/api/v1/visitor/recommend", json={"natural_language": "情侣两个人，预算1000，明天下雨，不想喝茶，不想逛博物馆，想看音乐现场"})
    assert response.status_code == 200, response.text
    interpreted = response.json()["interpreted_needs"]
    assert interpreted["target_crowd"] == "COUPLE"
    assert "TEA" in interpreted["negative_interests"]
    assert "CULTURE" in interpreted["negative_interests"]
    assert all("茶" not in item["product"]["product_name"] and "博物馆" not in item["product"]["product_name"] for item in response.json()["results"])


def test_public_reference_cannot_be_selected_for_formal_package(client, hotel_token):
    resources = client.get("/api/v1/hotel/resources", headers=auth(hotel_token)).json()
    public_reference = next(item for item in resources if item["source_type"] == "PUBLIC_REFERENCE")
    rooms = client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json()
    response = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json={
        "target_date": rooms[0]["available_date"],
        "weather": "RAIN",
        "target_crowd": "FAMILY",
        "theme": "公共参考测试",
        "room_inventory_id": rooms[0]["id"],
        "resource_selections": [{"resource_type": "PARTNER_RESOURCE", "resource_id": public_reference["id"], "quantity_per_package": 1}],
        "preferred_price": "699",
        "visitor_budget": "900",
    })
    assert response.status_code == 400
