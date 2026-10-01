from types import SimpleNamespace


def test_link_check_does_not_verify_facts_and_operator_can_review(client, hotel_token, monkeypatch):
    import httpx

    from app.services.knowledge_service import KnowledgeService

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: SimpleNamespace(status_code=200))
    headers = {"Authorization": f"Bearer {hotel_token}"}
    listing = client.get("/api/v1/hotel/knowledge", headers=headers)
    assert listing.status_code == 200
    record = listing.json()["items"][0]
    assert record["status"] == "VERIFY_REQUIRED"

    checked = client.post("/api/v1/hotel/knowledge/refresh", headers=headers)
    assert checked.status_code == 200
    assert checked.json()["reachable_count"] > 0
    assert checked.json()["facts_reverified"] == 0
    after_check = client.get("/api/v1/hotel/knowledge", headers=headers).json()
    record = next(item for item in after_check["items"] if item["id"] == record["id"])
    assert record["status"] == "VERIFY_REQUIRED"
    assert record["source_reachable"] is True
    assert record["source_checked_at"]

    reviewed_fields = [
        "name", "category", "area", "address", "indoor_outdoor", "suitable_crowds",
        "minimum_age", "maximum_age", "suggested_duration_minutes", "opening_hours",
        "weather_adaptations", "reservation_notice", "description", "source_name", "source_url",
    ]
    verified = client.post(
        f"/api/v1/hotel/knowledge/{record['id']}/verify",
        headers=headers,
        json={"reviewed_fields": reviewed_fields, "review_note": "已对照官方来源逐项确认记录内容"},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["item"]["verification_status"] == "ACTIVE"
    refreshed = client.get("/api/v1/hotel/knowledge", headers=headers).json()
    record = next(item for item in refreshed["items"] if item["id"] == record["id"])
    assert record["status"] == "ACTIVE"
    assert record["verified_by_user_id"]
    assert record["verification_note"] == "已对照官方来源逐项确认记录内容"


def test_knowledge_review_requires_all_fields_and_source(client, hotel_token):
    headers = {"Authorization": f"Bearer {hotel_token}"}
    listing = client.get("/api/v1/hotel/knowledge", headers=headers).json()
    item_id = listing["items"][0]["id"]
    response = client.post(
        f"/api/v1/hotel/knowledge/{item_id}/verify",
        headers=headers,
        json={"reviewed_fields": ["name"], "review_note": "checked"},
    )
    assert response.status_code == 422
