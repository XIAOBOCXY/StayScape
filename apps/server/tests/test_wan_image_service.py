from pathlib import Path

from app.config import settings
from app.services.wan_image_service import WanImageService


class FakeResponse:
    def __init__(self, *, payload=None, content=b"", content_type="image/png", status_code=200):
        self._payload = payload or {}
        self.content = content
        self.headers = {"content-type": content_type}
        self.is_success = status_code < 400

    def json(self):
        return self._payload


def test_wan_image_is_downloaded_to_server_owned_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "wan_image_enabled", True)
    monkeypatch.setattr(settings, "qwen_api_key", "test-key")
    monkeypatch.setattr(settings, "wan_image_api_key", "")
    monkeypatch.setattr(settings, "wan_image_workspace_id", "workspace-test")
    monkeypatch.setattr(settings, "wan_image_region", "cn-beijing")
    monkeypatch.setattr(settings, "wan_image_api_url", "")
    monkeypatch.setattr(settings, "generated_media_dir", str(tmp_path))
    monkeypatch.setattr(settings, "generated_media_url_path", "/generated-media")

    def fake_post(*_args, **_kwargs):
        return FakeResponse(payload={"request_id": "req-1", "output": {"choices": [{"message": {"content": [{"type": "image", "image": "https://dashscope-test.oss-cn-beijing.aliyuncs.com/result.png"}]}}]}})

    monkeypatch.setattr("app.services.wan_image_service.httpx.post", fake_post)
    monkeypatch.setattr("app.services.wan_image_service.httpx.get", lambda *_args, **_kwargs: FakeResponse(content=b"png-bytes"))

    result = WanImageService().generate("杭州周末主视觉")

    assert result["image_url"].startswith("/generated-media/wan-")
    assert result["image_model"] == "wan2.7-image"
    assert list(tmp_path.iterdir())[0].read_bytes() == b"png-bytes"


def test_wan_retries_once_with_a_neutral_visual_after_output_safety_block(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "wan_image_enabled", True)
    monkeypatch.setattr(settings, "qwen_api_key", "test-key")
    monkeypatch.setattr(settings, "wan_image_api_key", "")
    monkeypatch.setattr(settings, "wan_image_workspace_id", "workspace-test")
    monkeypatch.setattr(settings, "wan_image_region", "cn-beijing")
    monkeypatch.setattr(settings, "wan_image_api_url", "")
    monkeypatch.setattr(settings, "generated_media_dir", str(tmp_path))
    requests = []

    def fake_post(*_args, **kwargs):
        requests.append(kwargs["json"])
        if len(requests) == 1:
            return FakeResponse(payload={"code": "DataInspectionFailed", "message": "output blocked", "request_id": "blocked-1"}, status_code=400)
        return FakeResponse(payload={"request_id": "safe-2", "output": {"choices": [{"message": {"content": [{"type": "image", "image": "https://dashscope-test.oss-cn-beijing.aliyuncs.com/result.png"}]}}]}})

    monkeypatch.setattr("app.services.wan_image_service.httpx.post", fake_post)
    monkeypatch.setattr("app.services.wan_image_service.httpx.get", lambda *_args, **_kwargs: FakeResponse(content=b"safe-png"))

    result = WanImageService().generate("A travel portrait with museum visit")

    assert len(requests) == 2
    assert "No people" in requests[1]["input"]["messages"][0]["content"][0]["text"]
    assert result["image_safety_retry"] is True
