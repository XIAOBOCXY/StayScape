import json

import httpx

from app.agent.context import RequestContext
from app.agent.openclaw import OpenClawAgent
from app.agent.orchestrator import AgentOrchestrator
from app.config import settings


def test_openclaw_uses_only_responses_with_gateway_auth_and_agent_route(monkeypatch):
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
    agent = OpenClawAgent("http://gateway.local", "secret", "openclaw/default", 3, agent_id="stayscape-main")
    result = agent.generate(
        "stayscape-visitor-matcher",
        {"question": "雨天还能玩吗"},
        trace_id="trace_test",
        session_key="visitor:conversation-a",
    )
    assert result == '{"answer": "gateway ok"}'
    assert calls[0][0] == "http://gateway.local/v1/responses"
    body = calls[0][1]["json"]
    assert body["model"] == "openclaw/default"
    assert body["metadata"]["skill_name"] == "stayscape-visitor-matcher"
    assert body["metadata"]["trace_id"] == "trace_test"
    assert "stayscape-visitor-matcher" in body["input"][0]["content"][0]["text"]
    assert calls[0][1]["headers"]["Authorization"] == "Bearer secret"
    assert calls[0][1]["headers"]["x-openclaw-agent-id"] == "stayscape-main"
    assert calls[0][1]["headers"]["x-openclaw-session-key"] == "visitor:conversation-a"
    assert "text" not in body or "format" not in body.get("text", {})


def test_openclaw_rejects_legacy_transport():
    try:
        OpenClawAgent("http://gateway.local", "secret", "openclaw/default", 3, transport="gateway_tools")
    except ValueError as exc:
        assert "responses" in str(exc)
    else:
        raise AssertionError("legacy OpenClaw transports must not be accepted")


def test_openclaw_agent_target_is_sent_as_route_target_not_primary_model():
    agent = OpenClawAgent("http://gateway.local", "secret", "openclaw/default", 3)
    body = agent._responses_body(skill_name="stayscape-product-generator", payload={}, trace_id="trace-test")
    assert body["model"] == "openclaw/default"
    assert "qwen/qwen3.5-plus" not in json.dumps(body)


def test_request_context_session_keys_are_isolated():
    visitor_a = RequestContext(source_channel="WEB_VISITOR", actor_role="VISITOR", conversation_id="a")
    visitor_b = RequestContext(source_channel="WEB_VISITOR", actor_role="VISITOR", conversation_id="b")
    hotel_a = RequestContext(source_channel="WEB_HOTEL", actor_role="HOTEL_OPERATOR", hotel_id=7, conversation_id="a")
    feishu_a = RequestContext(source_channel="FEISHU", actor_role="HOTEL_OPERATOR", hotel_id=7, conversation_id="a")
    assert visitor_a.session_key == "visitor:a"
    assert visitor_b.session_key == "visitor:b"
    assert visitor_a.session_key != visitor_b.session_key
    assert hotel_a.session_key == "hotel:7:a"
    assert feishu_a.session_key == "feishu:7:a"


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
        result = AgentOrchestrator(db, provider=provider, hotel_id=7).match_visitor({"natural_language": "雨天带孩子"})
        assert provider.calls == 2
        assert result.retry_count == 1
        assert result.status == "SUCCESS"
        assert db.items[0].hotel_id == 7
        assert db.items[0].source_channel == "WEB_HOTEL"
        assert db.items[0].actor_role == "HOTEL_OPERATOR"
    finally:
        settings.agent_max_retries = old_retries
