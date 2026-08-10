from app.services.poster_service import render_poster_svg, wrap_text

from .test_api_flow import auth, generate_request


def test_interpret_returns_complete_timing_and_manual_fields(client):
    response = client.post("/api/v1/visitor/interpret", json={"natural_language": "两大两小，孩子6岁和9岁，周六下午三点到店，下午四点体验，下雨，预算1000"})
    assert response.status_code == 200, response.text
    needs = response.json()["interpreted_needs"]
    assert needs["target_date"]
    assert needs["arrival_time"] == "15:00"
    assert needs["preferred_experience_time"] == "16:00"
    assert needs["adult_count"] == 2 and needs["child_count"] == 2
    assert needs["activity_level"] == "MEDIUM"


def test_structured_confirmation_overrides_original_natural_language(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    product = generated.json()["product"]
    client.patch(f"/api/v1/hotel/products/{product['id']}/status", headers=auth(hotel_token), json={"status": "ON_SALE"})
    response = client.post("/api/v1/visitor/recommend", json={
        "natural_language": "两大两小，孩子6岁和9岁，预算1000，下雨",
        "structured_confirmed": True,
        "target_date": request["target_date"], "weather": "RAIN", "target_crowd": "FAMILY",
        "adult_count": 3, "child_count": 0, "child_ages": [], "budget": "700",
        "interests": ["手工"], "negative_interests": ["TEA"], "activity_level": "LOW",
        "arrival_time": "15:00", "preferred_experience_time": "16:00",
    })
    assert response.status_code == 200, response.text
    needs = response.json()["interpreted_needs"]
    assert needs["adult_count"] == 3
    assert needs["child_count"] == 0
    assert needs["negative_interests"] == ["TEA"]
    assert needs["arrival_time"] == "15:00"


def test_intent_persists_confirmed_group_instead_of_reparsing(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    product = generated.json()["product"]
    client.patch(f"/api/v1/hotel/products/{product['id']}/status", headers=auth(hotel_token), json={"status": "ON_SALE"})
    response = client.post("/api/v1/visitor/intents", json={
        "product_id": product["id"], "natural_language": "一家三口带一个6岁孩子",
        "structured_confirmed": True, "adult_count": 3, "child_count": 0, "child_ages": [],
        "budget": "700", "contact_name": "结构化游客", "contact_phone": "13600136000",
    })
    assert response.status_code == 200, response.text
    intent = client.get("/api/v1/hotel/intents", headers=auth(hotel_token)).json()[0]
    assert intent["adult_count"] == 3
    assert intent["child_count"] == 0
    assert intent["natural_language"] == "一家三口带一个6岁孩子"


def test_poster_uses_media_and_safe_multilingual_wrapping():
    title = "杭州雨天亲子非遗文化体验与精品家庭套房长标题安全区测试"
    lines = wrap_text(title, 520, 56, max_lines=3)
    assert len(lines) <= 3
    assert all(len(line) > 0 for line in lines)
    family = render_poster_svg(title=title, subtitle="family", partner_name="室内非遗手作体验", room_name="亲子家庭房", address="杭州市西湖区一条很长的体验地址", price="599", target_crowd="FAMILY", theme="亲子非遗", weather="RAIN", media_data_uri="data:image/png;base64,AA==")
    night = render_poster_svg(title="运河夜游宿", subtitle="night", partner_name="运河夜游", room_name="湖景大床房", address="运河边", price="799", target_crowd="COUPLE", theme="夜游", weather="CLOUDY", variant_index=1, media_data_uri="data:image/png;base64,AA==")
    assert "<image " in family and "data:image/png;base64,AA==" in family
    assert 'data-category="family"' in family
    assert 'data-category="nightlife"' in night
    assert family != night
