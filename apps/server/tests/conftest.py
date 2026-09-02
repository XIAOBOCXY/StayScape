import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app import db as db_module  # noqa: E402
from app.db import configure_database  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed import seed_demo  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch):
    """Keep integration tests deterministic even when run inside a Live image.

    Production configuration intentionally forbids an OpenClaw-to-Mock
    fallback.  Tests exercise the FastAPI validation and persistence boundary
    with the deterministic adapter instead, while dedicated adapter tests mock
    their own HTTP calls explicitly.
    """
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "mode", "demo")
    monkeypatch.setattr(settings, "agent_provider", "mock")
    monkeypatch.setattr(settings, "openclaw_live_ready", False)
    monkeypatch.setattr(settings, "weather_enabled", False)


@pytest.fixture()
def client():
    configure_database("sqlite:///:memory:")
    Base.metadata.create_all(bind=db_module.engine)
    db = db_module.SessionLocal()
    seed_demo(db, reset=True)
    db.close()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def hotel_token(client):
    response = client.post("/api/v1/auth/login", json={"username": "hotel_demo", "password": "StayScape123!"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture()
def merchant_token(client):
    response = client.post("/api/v1/auth/login", json={"username": "merchant_craft", "password": "StayScape123!"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]
