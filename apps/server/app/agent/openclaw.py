from typing import Any

import httpx


class OpenClawAgent:
    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def _post(self, path: str, payload: dict[str, Any]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            f"{self.base_url}{path}",
            json={"model": self.model, **payload},
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and isinstance(data.get("output"), str):
            return data["output"]
        if isinstance(data, dict) and isinstance(data.get("content"), str):
            return data["content"]
        return response.text

    def generate(self, skill_name: str, payload: dict[str, Any]) -> str:
        return self._post("/v1/skills/invoke", {"skill_name": skill_name, "input": payload})

    def repair_json(self, skill_name: str, payload: dict[str, Any], raw_response: str) -> str:
        return self._post("/v1/skills/repair-json", {"skill_name": skill_name, "input": payload, "raw_response": raw_response})

