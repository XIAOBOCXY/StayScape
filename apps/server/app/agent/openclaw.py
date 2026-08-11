"""Official OpenClaw Gateway Responses client.

ClawHive is deliberately not a runtime provider. Skills may be published to
ClawHive, while production Web/H5 calls go to one self-hosted OpenClaw
Gateway and the single ``stayscape-main`` Agent.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


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
        operation = "repair the previous JSON response" if repair else "execute the requested Skill"
        task: dict[str, Any] = {
            "skill_name": skill_name,
            "skill_version": self.skill_version,
            "input": payload,
        }
        if repair:
            task["raw_response"] = raw_response
        instructions = (
            f"You are the single StayScape Agent `{self.agent_id}` on {self.runtime_label}. "
            f"Use the installed Skill `{skill_name}` (version {self.skill_version or 'configured'}) to {operation}. "
            "Return exactly one JSON object matching the Skill contract. "
            "Never invent inventory, capacity, cost, price, margin, dates, weather constraints or database state. "
            "FastAPI validates every ID and deterministic business value after this response."
        )
        return {
            "model": self.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": instructions}]},
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps(task, ensure_ascii=False)}]},
            ],
            "instructions": instructions,
            "store": False,
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
