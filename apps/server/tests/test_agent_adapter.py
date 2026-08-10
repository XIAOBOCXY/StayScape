import json

import httpx

from app.agent.openclaw import ClawHiveAgent, OpenClawAgent
from app.agent.orchestrator import AgentOrchestrator
from app.config import settings


def test_openclaw_defaults_to_agent_responses(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        text = '{"answer":"gateway ok"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": '{"answer": "gateway ok"}'}]}]}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    agent = OpenClawAgent("http://gateway.local", "secret", "openclaw/default", 3)
    assert agent.generate("stayscape-visitor-matcher", {"question": "雨天能玩吗"}, trace_id="trace_test") == '{"answer": "gateway ok"}'
    assert calls[0][0] == "http://gateway.local/v1/responses"
    body = calls[0][1]["json"]
    assert body["model"] == "openclaw/default"
    assert body["metadata"]["skill_name"] == "stayscape-visitor-matcher"
    assert body["metadata"]["trace_id"] == "trace_test"
    assert "stayscape-visitor-matcher" in body["input"][0]["content"][0]["text"]
    assert calls[0][1]["headers"]["Authorization"] == "Bearer secret"


def test_openclaw_gateway_tools_remains_explicit_compatibility_mode(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        text = '{"answer":"gateway ok"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"result": {"structuredContent": {"answer": "gateway ok"}}}

    monkeypatch.setattr(httpx, "post", lambda url, **kwargs: (calls.append((url, kwargs)) or Response()))
    agent = OpenClawAgent("http://gateway.local", "secret", "openclaw/default", 3, transport="gateway_tools")
    assert agent.generate("stayscape-visitor-matcher", {"question": "rain"}, trace_id="trace_compat") == '{"answer": "gateway ok"}'
    assert calls[0][0] == "http://gateway.local/tools/invoke"
    assert calls[0][1]["json"]["args"]["skill"] == "stayscape-visitor-matcher"


def test_clawhive_agent_keeps_provider_identity_and_responses_contract(monkeypatch):
    class Response:
        status_code = 200
        text = '{"answer":"ok"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"output_text": '{"answer":"ok"}'}

    calls = []
    monkeypatch.setattr(httpx, "post", lambda url, **kwargs: (calls.append((url, kwargs)) or Response()))
    agent = ClawHiveAgent("http://clawhive-bridge.local", "server-secret", "clawhive/default", 3, agent_id="lobster-1")
    assert agent.provider_name == "CLAWHIVE"
    assert agent.generate("stayscape-product-generator", {"target_crowd": "FAMILY"}, trace_id="trace_clawhive") == '{"answer":"ok"}'
    assert calls[0][0] == "http://clawhive-bridge.local/v1/responses"
    assert calls[0][1]["headers"]["x-openclaw-agent-id"] == "lobster-1"
    assert calls[0][1]["headers"]["x-openclaw-session-key"] == "main"


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
