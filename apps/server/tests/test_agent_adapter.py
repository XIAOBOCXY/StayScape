import json

import httpx

from app.agent.openclaw import OpenClawAgent
from app.agent.orchestrator import AgentOrchestrator
from app.config import settings


def test_openclaw_defaults_to_gateway_tools_invoke(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        text = '{"answer":"gateway ok"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"result": {"structuredContent": {"answer": "gateway ok"}}}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    agent = OpenClawAgent("http://gateway.local", "secret", "openclaw/default", 3)
    assert agent.generate("stayscape-visitor-matcher", {"question": "雨天能玩吗"}, trace_id="trace_test") == '{"answer": "gateway ok"}'
    assert calls[0][0] == "http://gateway.local/tools/invoke"
    body = calls[0][1]["json"]
    assert body["tool"] == "skill_invoke"
    assert body["args"]["skill"] == "stayscape-visitor-matcher"
    assert body["idempotencyKey"] == "trace_test"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer secret"


def test_agent_retries_httpx_timeout_at_request_level():
    class InMemoryLog:
        def __init__(self):
            self.items = []

        def add(self, item):
            self.items.append(item)

    class FlakyProvider:
        def __init__(self):
            self.calls = 0

        def generate(self, skill_name, payload):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ReadTimeout("temporary gateway timeout")
            return json.dumps({"answer": "recovered"})

        def repair_json(self, skill_name, payload, raw_response):
            raise AssertionError("format repair should not be called")

    old_retries = settings.agent_max_retries
    try:
        settings.agent_max_retries = 1
        db = InMemoryLog()
        provider = FlakyProvider()
        result = AgentOrchestrator(db, provider=provider, hotel_id=7).match_visitor({"natural_language": "雨天亲子"})
        assert provider.calls == 2
        assert result.retry_count == 1
        assert result.status == "SUCCESS"
        assert db.items[0].hotel_id == 7
    finally:
        settings.agent_max_retries = old_retries
