"""ClawHive-managed Agent adapter.

ClawHive is the platform where the Skill is uploaded and installed to a
lobster instance. The HTTP adapter talks to the configured Agent runtime
bridge; ``responses`` is the primary transport, while gateway-tools and
legacy skill transports remain explicit compatibility modes.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class OpenClawAgent:
    provider_name = "OPENCLAW"
    runtime_label = "an OpenClaw-compatible Agent runtime"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        *,
        transport: str = "responses",
        responses_path: str = "/v1/responses",
        invoke_path: str = "/tools/invoke",
        tool_name: str = "skill_invoke",
        session_key: str = "main",
        agent_id: str = "",
        skill_version: str = "",
        legacy_fallback: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport.lower().strip() or "responses"
        self.responses_path = responses_path if responses_path.startswith("/") else f"/{responses_path}"
        self.invoke_path = invoke_path if invoke_path.startswith("/") else f"/{invoke_path}"
        self.tool_name = tool_name
        self.session_key = session_key
        self.agent_id = agent_id
        self.skill_version = skill_version
        self.legacy_fallback = legacy_fallback

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        # Official OpenResponses routing uses headers for the target Agent and
        # optional session. Keep the JSON metadata as an audit aid only.
        if self.agent_id:
            headers["x-openclaw-agent-id"] = self.agent_id
        if self.session_key:
            headers["x-openclaw-session-key"] = self.session_key
        return headers

    @staticmethod
    def _content(value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = []
            for item in value:
                found = OpenClawAgent._content(item)
                if found:
                    parts.append(found)
            return "\n".join(parts) if parts else None
        if isinstance(value, dict):
            if isinstance(value.get("structuredContent"), (dict, list)):
                return json.dumps(value["structuredContent"], ensure_ascii=False)
            if isinstance(value.get("structured_content"), (dict, list)):
                return json.dumps(value["structured_content"], ensure_ascii=False)
            for key in ("output_text", "text"):
                if isinstance(value.get(key), str):
                    return value[key]
            for key in ("output", "content", "result", "response", "data", "choices"):
                if key in value:
                    found = OpenClawAgent._content(value[key])
                    if found:
                        return found
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

    def _responses_body(self, *, skill_name: str, payload: dict[str, Any], trace_id: str | None, repair: bool = False, raw_response: str = "") -> dict[str, Any]:
        operation = "repair the previous JSON response" if repair else "execute the requested Skill"
        task = {
            "skill_name": skill_name,
            "skill_version": self.skill_version,
            "input": payload,
        }
        if repair:
            task["raw_response"] = raw_response
        system = (
            f"You are the StayScape Agent running inside {self.runtime_label}. "
            f"Use the installed Skill `{skill_name}` (version {self.skill_version or 'configured'}) to {operation}. "
            "Return only one JSON object matching the Skill contract; do not invent inventory, cost, price or margin."
        )
        body: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system}]},
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps(task, ensure_ascii=False)}]},
            ],
            "text": {"format": {"type": "json_object"}},
            "store": False,
            "metadata": {"trace_id": trace_id or "", "skill_name": skill_name, "skill_version": self.skill_version},
        }
        if self.session_key:
            body["metadata"]["session_key"] = self.session_key
        return body

    def _gateway_body(self, *, skill_name: str, payload: dict[str, Any], trace_id: str | None, repair: bool = False, raw_response: str = "") -> dict[str, Any]:
        args: dict[str, Any] = {"skill": skill_name, "input": payload, "response_format": "json"}
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
        if self.transport in {"legacy", "skills_v1"}:
            return self._post("/v1/skills/invoke", self._legacy_body(skill_name=skill_name, payload=payload))
        if self.transport in {"gateway_tools", "tools"}:
            try:
                return self._post(self.invoke_path, self._gateway_body(skill_name=skill_name, payload=payload, trace_id=trace_id))
            except httpx.HTTPStatusError as exc:
                if not self.legacy_fallback or exc.response.status_code not in {404, 405}:
                    raise
                return self._post("/v1/skills/invoke", self._legacy_body(skill_name=skill_name, payload=payload))
        try:
            return self._post(self.responses_path, self._responses_body(skill_name=skill_name, payload=payload, trace_id=trace_id))
        except httpx.HTTPStatusError as exc:
            if not self.legacy_fallback or exc.response.status_code not in {404, 405}:
                raise
            return self._post(self.invoke_path, self._gateway_body(skill_name=skill_name, payload=payload, trace_id=trace_id))

    def repair_json(self, skill_name: str, payload: dict[str, Any], raw_response: str, trace_id: str | None = None) -> str:
        if self.transport in {"legacy", "skills_v1"}:
            return self._post("/v1/skills/repair-json", self._legacy_body(skill_name=skill_name, payload=payload, raw_response=raw_response))
        if self.transport in {"gateway_tools", "tools"}:
            try:
                return self._post(self.invoke_path, self._gateway_body(skill_name=skill_name, payload=payload, trace_id=trace_id, repair=True, raw_response=raw_response))
            except httpx.HTTPStatusError as exc:
                if not self.legacy_fallback or exc.response.status_code not in {404, 405}:
                    raise
                return self._post("/v1/skills/repair-json", self._legacy_body(skill_name=skill_name, payload=payload, raw_response=raw_response))
        try:
            return self._post(self.responses_path, self._responses_body(skill_name=skill_name, payload=payload, trace_id=trace_id, repair=True, raw_response=raw_response))
        except httpx.HTTPStatusError as exc:
            if not self.legacy_fallback or exc.response.status_code not in {404, 405}:
                raise
            return self._post(self.invoke_path, self._gateway_body(skill_name=skill_name, payload=payload, trace_id=trace_id, repair=True, raw_response=raw_response))

    def diagnostics(self) -> dict[str, Any]:
        result = {"configured": bool(self.base_url and self.agent_id), "reachable": False, "status_code": None, "error": ""}
        if not self.base_url:
            result["error"] = "Agent runtime base URL is not configured"
            return result
        last_status = None
        for health_path in ("/readyz", "/healthz", "/health"):
            try:
                response = httpx.get(f"{self.base_url}{health_path}", headers=self._headers(), timeout=min(self.timeout_seconds, 3))
                last_status = response.status_code
                if response.is_success:
                    result.update({"reachable": True, "status_code": response.status_code, "health_path": health_path})
                    break
            except Exception as exc:  # try the next compatible health endpoint
                result["error"] = type(exc).__name__
        if not result["reachable"]:
            result["status_code"] = last_status
            if last_status:
                result["error"] = f"Gateway returned HTTP {last_status}"
        return result


class ClawHiveAgent(OpenClawAgent):
    """Agent bridge used when the installed Skills are managed by ClawHive.

    ClawHive itself is the control plane; the request is sent to the
    configured lobster/Agent runtime endpoint. Keeping this as a separate
    provider makes logs and diagnostics honest while preserving the old
    OpenClaw-compatible adapter for existing deployments.
    """

    provider_name = "CLAWHIVE"
    runtime_label = "a ClawHive-managed lobster Agent"
