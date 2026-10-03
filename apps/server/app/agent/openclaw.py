"""Official OpenClaw Gateway Responses client.

ClawHive is deliberately not a runtime provider. Skills may be published to
ClawHive, while production Web/H5 calls go to one self-hosted OpenClaw
Gateway and the single ``stayscape-main`` Agent.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


_WORKFLOW_RULES = {
    "stayscape-product-generator": (
        "Design one travel product candidate from supplied facts only. Select only supplied "
        "room, service, and partner IDs. Preserve crowd, child-age, weather, time, and safety "
        "constraints. Write natural traveller-facing Chinese; do not expose backend operations "
        "or invent places, availability, prices, claims, or identifiers. Use tourism_planning_context only as strategy/case inspiration, "
        "not as evidence of local demand, live destination facts, or financial performance. Never copy case prices, dates, or rights. "
        "Make every variant distinct: anchor it in named supplied resources, one concrete moment, and a different emotional hook; avoid generic travel slogans. For SOCIAL_POST, write a first-person, friend-to-friend travel-seeding note with specific moments from supplied facts, not a merchant sales pitch and not a claimed verified review. For STORE_CARD, write the merchant-facing concise selling copy."
    ),
    "stayscape-visitor-matcher": (
        "Recommend only supplied available travel products. Match the visitor's interests, "
        "negative preferences, schedule, party size, child ages, budget, weather, and safety details. "
        "Treat supplied structured state and recent conversation turns as cumulative; preserve confirmed "
        "constraints across follow-ups and ask only for missing details that materially change safety or fit. "
        "Filter hard constraints before ranking soft preferences. Offer up to three meaningfully different "
        "eligible products; do not pad a short result set. Explain concrete fit and trade-offs from supplied "
        "facts, use supplied source names/status for destination claims, cite uncertainty plainly, and never invent routes, times, prices, IDs, or availability. "
        "Do not promise allergy safety or expose backend operations. Write concise, natural Chinese for travellers."
    ),
    "stayscape-marketing-writer": (
        "Refresh the marketing copy for an already-validated travel product. Use only the supplied "
        "product facts: name, theme, crowd, weather, date, room, services, partner resources and "
        "price. Write four channel-appropriate assets (poster brief, social post, short-video script, "
        "store card) in natural traveller-facing Chinese. Keep the poster a visual brief only with "
        "creative_angle and poster_style hints; never return an internet image URL as a supplied asset. "
        "Do not rewrite recommendation_reason or risk_message. Preserve allergy, child-age, weather and "
        "time risks without promising safety or availability."
    ),
}
_OUTPUT_CONTRACTS = {
    "stayscape-product-generator": (
        "Return exactly one JSON object. product_name, theme, target_crowd, marketing_title, "
        "marketing_content, recommendation_reason, and risk_message are strings; "
        "room_inventory_id is an integer; hotel_service_ids and partner_resource_ids are integer arrays; "
        "resource_quantities is an object mapping supplied resource IDs to integers; "
        "marketing_assets is an array of objects with platform, title, content, visual_brief, "
        "call_to_action, creative_angle, and poster_style fields. Each asset_type must be exactly one "
        "of POSTER, SOCIAL_POST, SHORT_VIDEO_SCRIPT, or STORE_CARD; never use Chinese type labels."
    ),
    "stayscape-visitor-matcher": (
        "Return exactly one JSON object with these exact JSON types: "
        '{"answer":"string","safety_notes":"string","selected_product_ids":[123],'
        '"reasons":{"123":"string"},"schedule_notes":{"123":[{"time":"14:00","content":"string"}]},'
        '"limited_adjustments":{"123":["string"]},"allergy_warning":"string"}. '
        "Use product ID strings as the keys in reasons, schedule_notes, and limited_adjustments. "
        "Do not use arrays for safety_notes, reasons, schedule_notes, or limited_adjustments."
    ),
    "stayscape-marketing-writer": (
        "Return exactly one JSON object. marketing_title, marketing_content, creative_angle, and "
        "poster_style are strings; marketing_assets is an array of objects with platform, title, "
        "content, visual_brief, call_to_action, creative_angle, and poster_style fields. Each "
        "asset_type must be exactly one of POSTER, SOCIAL_POST, SHORT_VIDEO_SCRIPT, or STORE_CARD; "
        "never use Chinese type labels. Do not return recommendation_reason or risk_message."
    ),
}


class OpenClawAgent:
    provider_name = "OPENCLAW"
    runtime_label = "the self-hosted OpenClaw Gateway"

    def __init__(
        self,
        base_url: str,
        gateway_token: str,
        model: str,
        timeout_seconds: float,
        *,
        transport: str = "responses",
        responses_path: str = "/v1/responses",
        agent_id: str = "stayscape-main",
        skill_version: str = "",
        primary_model: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.gateway_token = gateway_token
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport.lower().strip() or "responses"
        if self.transport != "responses":
            raise ValueError("OpenClaw production transport must be 'responses'")
        self.responses_path = responses_path if responses_path.startswith("/") else f"/{responses_path}"
        self.agent_id = agent_id or "stayscape-main"
        self.skill_version = skill_version
        # ``model`` is the OpenResponses routing target (normally
        # ``openclaw/default``).  Keep the selected backend model separately so
        # diagnostics and SkillCallLog do not confuse the two concepts.
        self.primary_model = primary_model

    def _headers(self, session_key: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.gateway_token:
            headers["Authorization"] = f"Bearer {self.gateway_token}"
        headers["x-openclaw-agent-id"] = self.agent_id
        if session_key:
            headers["x-openclaw-session-key"] = session_key
        return headers

    @staticmethod
    def _content(value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = [found for item in value if (found := OpenClawAgent._content(item))]
            return "\n".join(parts) if parts else None
        if isinstance(value, dict):
            for key in ("structuredContent", "structured_content"):
                if isinstance(value.get(key), (dict, list)):
                    return json.dumps(value[key], ensure_ascii=False)
            for key in ("output_text", "text"):
                if isinstance(value.get(key), str):
                    return value[key]
            for key in ("output", "content", "result", "response", "data", "choices"):
                if key in value:
                    found = OpenClawAgent._content(value[key])
                    if found:
                        return found
        return None

    def _post(self, body: dict[str, Any], *, session_key: str | None = None) -> str:
        if not self.base_url:
            raise RuntimeError("OpenClaw Gateway URL is not configured")
        response = httpx.post(
            f"{self.base_url}{self.responses_path}",
            json=body,
            headers=self._headers(session_key),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return self._content(data) or response.text

    def _responses_body(
        self,
        *,
        skill_name: str,
        payload: dict[str, Any],
        trace_id: str | None,
        repair: bool = False,
        raw_response: str = "",
    ) -> dict[str, Any]:
        operation = "repair the previous JSON response" if repair else "complete the travel workflow"
        workflow_id = (
            "visitor_matching"
            if skill_name == "stayscape-visitor-matcher"
            else "marketing_writing"
            if skill_name == "stayscape-marketing-writer"
            else "product_generation"
        )
        task: dict[str, Any] = {
            "workflow": workflow_id,
            "input": payload,
        }
        if repair:
            task["raw_response"] = raw_response
        workflow_rules = _WORKFLOW_RULES.get(
            skill_name, "Use only supplied facts and return strict JSON."
        )
        output_contract = _OUTPUT_CONTRACTS.get(
            skill_name, "Return exactly one JSON object matching the supplied workflow."
        )
        instructions = (
            f"You are the single StayScape Agent '{self.agent_id}' on {self.runtime_label}. "
            f"Run the installed Skill '{skill_name}' for this request. "
            f"Complete the supplied travel workflow in one response: {operation}. "
            f"Workflow rules: {workflow_rules} "
            "This bounded generation request has no state-changing tools. Use only supplied facts; when a required fact is absent, mark it unavailable instead of inventing it. "
            "Use only the facts and IDs supplied in the workflow input. "
            "Never expose inventory, capacity, cost, margin, rule engine, API, Demo, Mock, "
            "or internal IDs in visitor-facing Chinese. "
            f"Output requirement: {output_contract} "
            "Return JSON only, with no Markdown fence or explanatory text."
        )
        return {
            "model": self.model,
            "input": [
                {"type": "message", "role": "system", "content": [{"type": "input_text", "text": instructions}]},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": json.dumps(task, ensure_ascii=False)}]},
            ],
            "instructions": instructions,
            "store": False,
            "tool_choice": "none",
            "max_output_tokens": 6400 if skill_name == "stayscape-marketing-writer" else 3200,
            "metadata": {"trace_id": trace_id or "", "skill_name": skill_name, "skill_version": self.skill_version},
        }

    def generate(
        self,
        skill_name: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
        session_key: str | None = None,
    ) -> str:
        return self._post(self._responses_body(skill_name=skill_name, payload=payload, trace_id=trace_id), session_key=session_key)

    def repair_json(
        self,
        skill_name: str,
        payload: dict[str, Any],
        raw_response: str,
        trace_id: str | None = None,
        session_key: str | None = None,
    ) -> str:
        return self._post(
            self._responses_body(skill_name=skill_name, payload=payload, trace_id=trace_id, repair=True, raw_response=raw_response),
            session_key=session_key,
        )

    def diagnostics(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "configured": bool(self.base_url and self.gateway_token and self.agent_id),
            "reachable": False,
            "status_code": None,
            "health_path": None,
            "error": "",
        }
        if not self.base_url:
            result["error"] = "OpenClaw Gateway URL is not configured"
            return result
        last_status = None
        for health_path in ("/readyz", "/healthz", "/health"):
            try:
                response = httpx.get(f"{self.base_url}{health_path}", headers=self._headers(), timeout=min(self.timeout_seconds, 3))
                last_status = response.status_code
                if response.is_success:
                    result.update({"reachable": True, "status_code": response.status_code, "health_path": health_path})
                    break
            except Exception as exc:
                result["error"] = type(exc).__name__
        if not result["reachable"]:
            result["status_code"] = last_status
            if last_status:
                result["error"] = f"Gateway returned HTTP {last_status}"
        return result
