from app.config import settings


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
    intent = client.post("/api/v1/visitor/intents", json={"product_id": product["id"], "adult_count": 2, "child_count": 1, "child_ages": [6], "budget": "700", "interests": ["手工"], "allergy_information": "花生过敏", "contact_name": "张三", "contact_phone": "13800138000"})
    assert intent.status_code == 200, intent.text
    assert intent.json()["contact_phone_masked"] == "138****8000"


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
