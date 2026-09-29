from datetime import date, timedelta

import pytest

from app.services.poster_service import render_poster_svg, wrap_text
from app.services.product_advisor_service import ProductAdvisor

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


def test_interpret_does_not_fall_back_to_two_adults_for_group_phrases(client):
    friends = client.post("/api/v1/visitor/interpret", json={"natural_language": "三个朋友周末来杭州"})
    assert friends.status_code == 200
    assert friends.json()["interpreted_needs"]["adult_count"] == 3
    assert friends.json()["interpreted_needs"]["child_count"] == 0

    family = client.post("/api/v1/visitor/interpret", json={"natural_language": "一家四口，孩子6岁和9岁"})
    assert family.status_code == 200
    assert family.json()["interpreted_needs"]["adult_count"] == 2
    assert family.json()["interpreted_needs"]["child_count"] == 2


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


def test_refine_crowd_updates_product_name_and_party_size(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post('/api/v1/hotel/products/generate', headers=auth(hotel_token), json=request)
    assert generated.status_code == 200, generated.text
    product_id = generated.json()['product']['id']
    response = client.post(f'/api/v1/hotel/products/{product_id}/refine', headers=auth(hotel_token), json={'natural_language': '改成单人'})
    assert response.status_code == 200, response.text
    product = response.json()['product']
    assert product['target_crowd'] == 'SOLO'
    assert product['party_size'] == 1
    assert '独自旅行' in product['product_name']


def test_advisor_keeps_party_size_when_follow_up_changes_price(client, hotel_token):
    created = client.post('/api/v1/hotel/ai/conversations', headers=auth(hotel_token), json={'title': '回归测试'})
    assert created.status_code == 200, created.text
    conversation_id = created.json()['id']
    solo = client.post(f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor', headers=auth(hotel_token), json={'natural_language': '改成单人'})
    assert solo.status_code == 200, solo.text
    assert solo.json()['advisor']['primary']['party_size'] == 1
    priced = client.post(f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor', headers=auth(hotel_token), json={'natural_language': '价格做到500'})
    assert priced.status_code == 200, priced.text
    assert priced.json()['advisor']['primary']['party_size'] == 1


def test_advisor_route_instruction_returns_visible_route_note(client, hotel_token):
    created = client.post('/api/v1/hotel/ai/conversations', headers=auth(hotel_token), json={'title': '路线回归测试'})
    assert created.status_code == 200, created.text
    conversation_id = created.json()['id']
    response = client.post(f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor', headers=auth(hotel_token), json={'natural_language': '路线安排轻松一点，下午留自由时间'})
    assert response.status_code == 200, response.text
    primary = response.json()['advisor']['primary']
    assert primary.get('route_note')
    assert '自由' in primary['route_note']


def test_advisor_confirmation_preserves_solo_party_and_route_note(client, hotel_token):
    created = client.post('/api/v1/hotel/ai/conversations', headers=auth(hotel_token), json={'title': '确认状态回归测试'})
    assert created.status_code == 200, created.text
    conversation_id = created.json()['id']

    solo = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '改成单人'},
    )
    assert solo.status_code == 200, solo.text
    assert solo.json()['advisor']['primary']['party_size'] == 1

    routed = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '路线安排轻松一点，下午留自由时间'},
    )
    assert routed.status_code == 200, routed.text
    routed_primary = routed.json()['advisor']['primary']
    assert routed_primary['party_size'] == 1
    assert '自由' in routed_primary['route_note']

    generated = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '就这个，生成候选'},
    )
    assert generated.status_code == 200, generated.text
    payload = generated.json()
    assert payload['advisor']['step'] == 'GENERATED'
    assert payload['advisor']['primary']['party_size'] == 1
    assert '自由' in payload['advisor']['primary']['route_note']
    assert payload['proposals']
    assert all(item['product']['party_size'] == 1 for item in payload['proposals'])


def test_advisor_rejects_past_date_without_silently_changing_primary(client, hotel_token):
    created = client.post('/api/v1/hotel/ai/conversations', headers=auth(hotel_token), json={'title': '日期校验回归测试'})
    conversation_id = created.json()['id']
    initial = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '改成单人'},
    ).json()['advisor']['primary']
    past = date.today() - timedelta(days=1)

    rejected = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': f'改成{past.month}月{past.day}日'},
    )

    assert rejected.status_code == 200, rejected.text
    advisor = rejected.json()['advisor']
    assert advisor['validation_error']['code'] == 'DATE_PASSED'
    assert str(past.month) in advisor['validation_error']['message']
    assert 'primary' not in advisor
    assert advisor['plan']['target_date'] == initial['target_date']

    continued = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '路线安排轻松一点，下午留自由时间'},
    ).json()['advisor']['primary']
    assert continued['target_date'] == initial['target_date']
    assert continued['party_size'] == 1


def test_resource_names_do_not_change_explicit_audience():
    advisor = object.__new__(ProductAdvisor)
    parsed = advisor._parse('换成沉浸式城市演出，再加一个咖啡体验和博物馆导览', [])
    assert parsed['crowd'] == ''
    assert parsed['party_size'] is None


@pytest.mark.parametrize(
    ('instruction', 'crowd', 'party_size'),
    [
        ('改成单人套餐', 'SOLO', 1),
        ('改成情侣双人套餐', 'COUPLE', 2),
        ('改成亲子家庭套餐', 'FAMILY', 3),
        ('改成朋友同行套餐', 'FRIENDS', 3),
    ],
)
def test_advisor_parses_only_explicit_audience_phrases(instruction, crowd, party_size):
    advisor = object.__new__(ProductAdvisor)
    parsed = advisor._parse(instruction, [])
    assert parsed['crowd'] == crowd
    assert parsed['party_size'] == party_size


def test_route_word_does_not_accidentally_confirm_plan():
    advisor = object.__new__(ProductAdvisor)
    parsed = advisor._parse('行程安排轻松一点，下午留自由时间', [])
    assert parsed['confirm'] is False


def test_advisor_rejects_invalid_and_unavailable_dates(client, hotel_token):
    created = client.post('/api/v1/hotel/ai/conversations', headers=auth(hotel_token), json={'title': '日期边界回归测试'})
    conversation_id = created.json()['id']
    initial = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '改成单人'},
    ).json()['advisor']['primary']

    invalid = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '改成2月30日'},
    ).json()['advisor']
    assert invalid['validation_error']['code'] == 'DATE_INVALID'
    assert invalid['plan']['target_date'] == initial['target_date']

    unavailable_date = date.today() + timedelta(days=365)
    unavailable = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': f'改成{unavailable_date.isoformat()}'},
    ).json()['advisor']
    assert unavailable['validation_error']['code'] == 'DATE_UNAVAILABLE'
    assert unavailable['plan']['target_date'] == initial['target_date']

    routed = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '路线安排轻松一点，下午留自由时间'},
    )
    assert routed.status_code == 200, routed.text
    assert '自由' in routed.json()['advisor']['primary']['route_note']


def test_advisor_keeps_solo_budget_route_and_date_through_candidate_generation(client, hotel_token):
    created = client.post('/api/v1/hotel/ai/conversations', headers=auth(hotel_token), json={'title': '完整状态回归测试'})
    conversation_id = created.json()['id']

    solo = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '改成单人'},
    ).json()['advisor']['primary']
    target_date = solo['target_date']

    resource = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '换成沉浸式城市演出'},
    ).json()['advisor']['primary']
    assert resource['crowd'] == 'SOLO'
    assert resource['party_size'] == 1
    assert resource['target_date'] == target_date
    assert '沉浸式城市演出' not in [item['name'] for item in resource['experiences']]
    assert '不适合' in resource['selection_notice']

    budgeted = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '价格控制在800以内'},
    ).json()['advisor']['primary']
    assert budgeted['visitor_budget'] == '800.00'
    assert float(budgeted['price']) <= 800

    routed = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '路线安排轻松一点，下午留自由时间'},
    ).json()['advisor']['primary']
    assert routed['crowd'] == 'SOLO'
    assert routed['party_size'] == 1
    assert routed['target_date'] == target_date
    assert routed['visitor_budget'] == '800.00'
    assert float(routed['price']) <= 800
    assert '自由' in routed['route_note']

    generated = client.post(
        f'/api/v1/hotel/ai/conversations/{conversation_id}/advisor',
        headers=auth(hotel_token),
        json={'natural_language': '就这个，生成候选'},
    )
    assert generated.status_code == 200, generated.text
    payload = generated.json()
    assert payload['advisor']['step'] == 'GENERATED'
    assert payload['proposals']
    for proposal in payload['proposals']:
        product = proposal['product']
        assert product['target_date'] == target_date
        assert product['target_crowd'] == 'SOLO'
        assert product['party_size'] == 1
        assert float(product['suggested_price']) <= 800

def test_refine_product_adds_named_experience_and_hotel_service(client, hotel_token, merchant_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post('/api/v1/hotel/products/generate', headers=auth(hotel_token), json=request)
    assert generated.status_code == 200, generated.text
    product = generated.json()['product']
    product_id = product['id']
    target_date = product['target_date']

    experience_name = '夜间回归文化体验'
    created_resource = client.post('/api/v1/merchant/resources', headers=auth(merchant_token), json={
        'resource_name': experience_name,
        'category': 'CULTURE',
        'description': '用于验证已生成产品可增加体验的夜间文化活动',
        'available_date': target_date,
        'start_time': '20:00',
        'end_time': '21:00',
        'remaining_capacity': 24,
        'settlement_price': '35',
        'market_price': '68',
        'suitable_crowds': 'FAMILY',
        'minimum_age': 3,
        'maximum_age': 70,
        'indoor': True,
        'weather_tags': 'RAIN,SUNNY,CLOUDY',
        'address': '杭州市西湖区文三路88号测试文化馆夜间活动厅',
        'package_enabled': True,
    })
    assert created_resource.status_code == 200, created_resource.text

    experience_result = client.post(
        f'/api/v1/hotel/products/{product_id}/refine',
        headers=auth(hotel_token),
        json={'natural_language': f'增加体验：{experience_name}'},
    )
    assert experience_result.status_code == 200, experience_result.text
    experience_payload = experience_result.json()
    assert experience_payload['layer'] == 'EQUITY'
    assert experience_name in [
        item['resource_name'] for item in experience_payload['product']['resources']
        if item['resource_type'] == 'PARTNER_RESOURCE'
    ]

    service_name = '夜间欢迎饮品回归权益'
    created_service = client.post('/api/v1/hotel/services', headers=auth(hotel_token), json={
        'service_name': service_name,
        'service_type': 'OTHER',
        'available_date': target_date,
        'available_quantity': 24,
        'unit_cost': '12',
        'reference_price': '28',
        'suitable_crowds': 'FAMILY',
    })
    assert created_service.status_code == 200, created_service.text

    service_result = client.post(
        f'/api/v1/hotel/products/{product_id}/refine',
        headers=auth(hotel_token),
        json={'natural_language': f'增加酒店权益：{service_name}'},
    )
    assert service_result.status_code == 200, service_result.text
    assert service_name in [
        item['resource_name'] for item in service_result.json()['product']['resources']
        if item['resource_type'] == 'HOTEL_SERVICE'
    ]

def test_refine_route_persists_visible_free_time(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post('/api/v1/hotel/products/generate', headers=auth(hotel_token), json=request)
    assert generated.status_code == 200, generated.text
    product_id = generated.json()['product']['id']

    response = client.post(
        f'/api/v1/hotel/products/{product_id}/refine',
        headers=auth(hotel_token),
        json={'natural_language': '路线安排轻松一点，下午留自由时间'},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['layer'] == 'EXPERIENCE'
    assert any(item['field'] == 'route_plan' for item in payload['changes'])
    titles = [item['title'] for day in payload['product']['day_plan'] for item in day['items']]
    assert '自由活动（自主安排）' in titles

def test_refine_product_swap_returns_recalculated_resources(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post('/api/v1/hotel/products/generate', headers=auth(hotel_token), json=request)
    assert generated.status_code == 200, generated.text
    product_id = generated.json()['product']['id']
    response = client.post(f'/api/v1/hotel/products/{product_id}/refine', headers=auth(hotel_token), json={'natural_language': '换成儿童茶文化课堂'})
    assert response.status_code == 200, response.text
    payload = response.json()
    partner_names = [item['resource_name'] for item in payload['product']['resources'] if item['resource_type'] == 'PARTNER_RESOURCE']
    assert any(item['field'] == 'partner_resource' for item in payload['changes']), payload['message']
    assert partner_names == ['儿童茶文化课堂']
    assert int(payload['product']['sale_quantity']) > 0

def test_advisor_never_recommends_room_below_party_capacity(client, hotel_token):
    created = client.post('/api/v1/hotel/ai/conversations', headers=auth(hotel_token), json={'title': '容量回归测试'})
    assert created.status_code == 200, created.text
    response = client.post(f"/api/v1/hotel/ai/conversations/{created.json()['id']}/advisor", headers=auth(hotel_token), json={'natural_language': '亲子家庭，一家三口，周末住一晚'})
    assert response.status_code == 200, response.text
    primary = response.json()['advisor']['primary']
    assert primary['party_size'] == 3
    rooms = client.get('/api/v1/hotel/rooms', headers=auth(hotel_token)).json()
    selected = next(item for item in rooms if item['room_type'] == primary['room_type'] and item['available_date'] == primary['target_date'])
    assert int(selected['max_guests']) >= int(primary['party_size'])
