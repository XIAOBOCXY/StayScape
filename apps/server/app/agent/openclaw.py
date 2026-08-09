"""OpenClaw Gateway adapter with a small legacy compatibility bridge.

The current Gateway exposes tool invocation at ``POST /tools/invoke``.  A
deployment can still opt into the old skill HTTP paths while migrating, but
the standard transport is the default and every request carries the same
trace/idempotency context used by the business log.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class OpenClawAgent:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        *,
        transport: str = "gateway_tools",
        invoke_path: str = "/tools/invoke",
        tool_name: str = "skill_invoke",
        session_key: str = "main",
        agent_id: str = "",
        legacy_fallback: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.invoke_path = invoke_path if invoke_path.startswith("/") else f"/{invoke_path}"
        self.tool_name = tool_name
        self.session_key = session_key
        self.agent_id = agent_id
        self.legacy_fallback = legacy_fallback

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _content(value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts) if parts else None
        if isinstance(value, dict):
            for key in ("structuredContent", "structured_content"):
                if key in value and isinstance(value[key], (dict, list)):
                    return json.dumps(value[key], ensure_ascii=False)
            for key in ("output", "content", "text", "result", "response", "data", "structuredContent", "structured_content"):
                found = OpenClawAgent._content(value.get(key))
                if found:
                    return found
            choices = value.get("choices")
            if isinstance(choices, list) and choices:
                return OpenClawAgent._content(choices[0])
        return None

    def _post(self, path: str, body: dict[str, Any]) -> str:
        response = httpx.post(
            f"{self.base_url}{path}",
            json=body,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return self._content(data) or response.text

    def _gateway_body(self, *, skill_name: str, payload: dict[str, Any], trace_id: str | None, repair: bool = False, raw_response: str = "") -> dict[str, Any]:
        args: dict[str, Any] = {
            "skill": skill_name,
            "input": payload,
            "response_format": "json",
        }
        if repair:
            args.update({"operation": "repair_json", "raw_response": raw_response})
        body: dict[str, Any] = {"tool": self.tool_name, "action": "invoke", "args": args}
        if self.session_key:
            body["sessionKey"] = self.session_key
        if self.agent_id:
            body["agentId"] = self.agent_id
        if trace_id:
            body["idempotencyKey"] = trace_id
        return body

    def _legacy_body(self, *, skill_name: str, payload: dict[str, Any], raw_response: str = "") -> dict[str, Any]:
        body = {"model": self.model, "skill_name": skill_name, "input": payload}
        if raw_response:
            body["raw_response"] = raw_response
        return body

    def generate(self, skill_name: str, payload: dict[str, Any], trace_id: str | None = None) -> str:
        if self.transport.lower() in {"legacy", "skills_v1"}:
            return self._post("/v1/skills/invoke", self._legacy_body(skill_name=skill_name, payload=payload))
        try:
            return self._post(self.invoke_path, self._gateway_body(skill_name=skill_name, payload=payload, trace_id=trace_id))
        except httpx.HTTPStatusError as exc:
            if not self.legacy_fallback or exc.response.status_code not in {404, 405}:
                raise
            return self._post("/v1/skills/invoke", self._legacy_body(skill_name=skill_name, payload=payload))

    def repair_json(self, skill_name: str, payload: dict[str, Any], raw_response: str, trace_id: str | None = None) -> str:
        if self.transport.lower() in {"legacy", "skills_v1"}:
            return self._post("/v1/skills/repair-json", self._legacy_body(skill_name=skill_name, payload=payload, raw_response=raw_response))
        try:
            return self._post(self.invoke_path, self._gateway_body(skill_name=skill_name, payload=payload, trace_id=trace_id, repair=True, raw_response=raw_response))
        except httpx.HTTPStatusError as exc:
            if not self.legacy_fallback or exc.response.status_code not in {404, 405}:
                raise
            return self._post("/v1/skills/repair-json", self._legacy_body(skill_name=skill_name, payload=payload, raw_response=raw_response))
