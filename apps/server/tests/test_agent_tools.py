from app.config import settings


def tool_headers(settings, *, role="HOTEL_SUPPORT", sender="ou_operator", hotel_id="1"):
    return {
        "Authorization": "Bearer tool-secret",
        "X-StayScape-Source-Channel": "FEISHU",
        "X-StayScape-Actor-Role": role,
        "X-StayScape-Hotel-Id": hotel_id,
        "X-StayScape-Sender-Id": sender,
        "X-StayScape-Conversation-Id": "feishu-conversation-1",
    }


def configure_tool_auth(monkeypatch, settings):
    monkeypatch.setattr(settings, "stayscape_agent_tool_token", "tool-secret")
    monkeypatch.setattr(settings, "feishu_dm_allow_from", "ou_operator")


def test_agent_tools_fail_closed_without_server_token(client, monkeypatch):
    configure_tool_auth(monkeypatch, settings)
    response = client.post(
        "/api/v1/agent-tools/hotel-context",
        headers={**tool_headers(settings), "Authorization": "Bearer wrong"},
        json={"hotel_id": 1, "payload": {}},
    )
    assert response.status_code == 401


def test_agent_tools_require_feishu_allowlisted_context(client, monkeypatch):
    configure_tool_auth(monkeypatch, settings)
    response = client.post(
        "/api/v1/agent-tools/hotel-context",
        headers=tool_headers(settings, sender="ou_unknown"),
        json={"hotel_id": 1, "payload": {}},
    )
    assert response.status_code == 403
    response = client.post(
        "/api/v1/agent-tools/hotel-context",
        headers={**tool_headers(settings), "X-StayScape-Source-Channel": "WEB_VISITOR"},
        json={"hotel_id": 1, "payload": {}},
    )
    assert response.status_code == 403


def test_agent_tool_returns_hotel_context_and_visitor_safe_products(client, monkeypatch):
    configure_tool_auth(monkeypatch, settings)
    context = client.post(
        "/api/v1/agent-tools/hotel-context",
        headers=tool_headers(settings),
        json={"hotel_id": 1, "payload": {}},
    )
    assert context.status_code == 200, context.text
    body = context.json()
    assert body["hotel_id"] == 1
    assert body["rooms"]
    assert body["partner_resources"]
    assert "cost" not in body["rooms"][0]
    assert "unit_cost" not in body["services"][0]
    assert "settlement_price" not in body["partner_resources"][0]

    products = client.post(
        "/api/v1/agent-tools/available-products",
        headers=tool_headers(settings),
        json={"hotel_id": 1, "payload": {"budget": "700"}},
    )
    assert products.status_code == 200, products.text
    if products.json()["items"]:
        item = products.json()["items"][0]
        assert {"id", "product_name", "price", "sale_quantity", "resources"} <= set(item)
        assert "gross_margin" not in item
        assert "unit_cost" not in item


def test_visitor_or_support_cannot_create_product_draft(client, monkeypatch):
    configure_tool_auth(monkeypatch, settings)
    response = client.post(
        "/api/v1/agent-tools/product-draft",
        headers=tool_headers(settings, role="HOTEL_SUPPORT"),
        json={"hotel_id": 1, "payload": {}},
    )
    assert response.status_code == 403
