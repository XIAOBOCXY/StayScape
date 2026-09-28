"""Editable integration settings for the hotel workbench.

The deployment ships sensible defaults (DeepSeek for reasoning, Wan for image
generation).  An operator can override the model names, endpoints and keys from
the workbench; the values live in a JSON file inside the persisted media volume
so they survive container rebuilds and can be exported with the demo data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import settings


SETTINGS_FILE = Path(settings.generated_media_dir) / "runtime-settings.json"

DEFAULTS: dict[str, Any] = {
    "agent_provider": settings.agent_provider,
    "openclaw_base_url": settings.openclaw_base_url,
    "primary_model": settings.openclaw_primary_model or "deepseek/deepseek-v4-flash",
    "reasoning_provider": "deepseek",
    "deepseek_api_key": "",
    "vision_provider": "qwen",
    "vision_api_key": "",
    "image_model": settings.wan_image_model,
    "image_api_key": "",
    "image_workspace_id": settings.wan_image_workspace_id,
    "image_enabled": bool(settings.wan_image_enabled),
}


def _mask(value: str) -> str:
    text = str(value or "")
    if len(text) <= 8:
        return "已配置" if text else "未配置"
    return f"{text[:4]}****{text[-4:]}"


def load_settings() -> dict[str, Any]:
    data = dict(DEFAULTS)
    if SETTINGS_FILE.is_file():
        try:
            data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    for secret_key in ("deepseek_api_key", "vision_api_key", "image_api_key"):
        data[secret_key] = ""
    return data


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    data = load_settings()
    for key, value in updates.items():
        # API credentials are server environment secrets. Do not persist a
        # browser-supplied copy in the generated-media volume.
        if key.endswith("_api_key"):
            continue
        if key not in DEFAULTS or value in (None, ""):
            continue
        data[key] = value
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        SETTINGS_FILE.chmod(0o600)
    except OSError:
        pass
    return data


def public_settings() -> dict[str, Any]:
    """Everything the workbench may show: values, plus masked key previews."""

    data = load_settings()
    return {
        **{key: value for key, value in data.items() if not key.endswith("_api_key")},
        "reasoning_key_preview": _mask(str(data.get("deepseek_api_key") or "")),
        "vision_key_preview": _mask(str(data.get("vision_api_key") or "")),
        "image_key_preview": _mask(str(data.get("image_api_key") or settings.wan_image_api_key or "")),
        "configured": {
            "reasoning": bool(data.get("deepseek_api_key") or settings.deepseek_api_key),
            "vision": bool(data.get("vision_api_key") or settings.qwen_api_key),
            "image": bool(data.get("image_api_key") or settings.wan_image_api_key),
        },
    }
