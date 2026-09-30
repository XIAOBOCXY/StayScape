"""A retried visitor submission must never reserve inventory twice."""

from sqlalchemy import func, select

from app import db as db_module
from app.models import VisitorIntent
from tests.test_api_flow import auth, generate_request


def _on_sale_product(client, hotel_token):
    request, _ = generate_request(client, hotel_token)
    generated = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    assert generated.status_code == 200, generated.text
    product = generated.json()["product"]
    status = client.patch(
        f"/api/v1/hotel/products/{product['id']}/status",
        headers=auth(hotel_token),
        json={"status": "ON_SALE"},
    )
    assert status.status_code == 200, status.text
    return request, product


def _room_count(client, hotel_token, room_id):
    rooms = client.get("/api/v1/hotel/rooms", headers=auth(hotel_token)).json()
    return next(item for item in rooms if item["id"] == room_id)["available_count"]


def _payload(product_id, key):
    payload = {
        "product_id": product_id,
        "adult_count": 2,
        "child_count": 1,
        "child_ages": [6],
        "budget": "700",
        "contact_name": "Repeat Guest",
        "contact_phone": "13700137001",
    }
    if key is not None:
        payload["client_request_id"] = key
    return payload


def test_retrying_with_the_same_key_reserves_inventory_once(client, hotel_token):
    request, product = _on_sale_product(client, hotel_token)
    room_id = request["room_inventory_id"]

    first = client.post("/api/v1/visitor/intents", json=_payload(product["id"], "retry-key-1"))
    assert first.status_code == 200, first.text
    after_first = _room_count(client, hotel_token, room_id)

    replay = client.post("/api/v1/visitor/intents", json=_payload(product["id"], "retry-key-1"))
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == first.json()["id"]
    assert _room_count(client, hotel_token, room_id) == after_first

    db = db_module.SessionLocal()
    try:
        stored = db.scalar(
            select(func.count(VisitorIntent.id)).where(VisitorIntent.client_request_id == "retry-key-1")
        )
        assert stored == 1
    finally:
        db.close()


def test_distinct_keys_create_distinct_orders(client, hotel_token):
    request, product = _on_sale_product(client, hotel_token)
    room_id = request["room_inventory_id"]
    before = _room_count(client, hotel_token, room_id)

    first = client.post("/api/v1/visitor/intents", json=_payload(product["id"], "retry-key-a"))
    second = client.post("/api/v1/visitor/intents", json=_payload(product["id"], "retry-key-b"))

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] != second.json()["id"]
    assert _room_count(client, hotel_token, room_id) == before - 2


def test_submission_without_a_key_still_works(client, hotel_token):
    _, product = _on_sale_product(client, hotel_token)

    response = client.post("/api/v1/visitor/intents", json=_payload(product["id"], None))

    assert response.status_code == 200, response.text
    assert response.json()["product_id"] == product["id"]
