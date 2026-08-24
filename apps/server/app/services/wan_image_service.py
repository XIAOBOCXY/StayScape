"""Server-only client for optional Alibaba Cloud Bailian Wan image generation."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
import logging

import httpx

from ..config import settings
from ..core.exceptions import AppError

SUPPORTED_WAN_MODELS = {"wan2.7-image", "wan2.7-image-pro"}
_ALLOWED_OUTPUT_HOST_SUFFIXES = (".aliyuncs.com",)
logger = logging.getLogger(__name__)


class WanImageService:
    def _api_key(self) -> str:
        return (settings.wan_image_api_key or settings.qwen_api_key).strip()

    def _api_url(self) -> str:
        url = settings.resolved_wan_image_api_url
        # The old global DashScope endpoint is not the Wan 2.7 workspace API.
        # Reject it with an actionable message instead of making a request that
        # the browser will only see as a generic failure.
        if not url or urlparse(url).hostname == "dashscope.aliyuncs.com":
            raise AppError(
                "WAN_IMAGE_WORKSPACE_REQUIRED",
                "万相 2.7 需要百炼工作空间 ID；请在服务器 .env 填写 WAN_IMAGE_WORKSPACE_ID 后重新部署。",
                status_code=503,
                retryable=False,
                suggestion="在百炼工作空间概览复制 Workspace ID；北京地域保留 WAN_IMAGE_REGION=cn-beijing。",
            )
        return url

    @staticmethod
    def _safe_retry_prompt() -> str:
        """A neutral fallback for rare output-side safety false positives.

        The normal request remains product-specific.  This is only used after
        BaiLian has already accepted the request but rejected its own rendered
        result, so a merchant does not have to retry a perfectly ordinary
        travel campaign by hand.
        """
        return (
            "A calm, family-safe editorial travel photograph in Hangzhou, China. "
            "Show only architecture, landscape, museum interiors, craft objects, "
            "food still life, or scenic streets. No people, faces, body parts, text, "
            "watermarks, logos, posters, graffiti, or signage. Vertical composition "
            "with generous clean space and natural daylight."
        )

    @staticmethod
    def _provider_failure(response: httpx.Response) -> tuple[str, str, str]:
        try:
            failure = response.json()
        except ValueError:
            failure = {}
        return (
            str(failure.get("code") or f"HTTP_{response.status_code}")[:80],
            str(failure.get("message") or "服务暂时未完成")[:260],
            str(failure.get("request_id") or response.headers.get("x-request-id") or "")[:120],
        )

    @staticmethod
    def _payload(model: str, prompt: str) -> dict:
        return {
            "model": model,
            "input": {"messages": [{"role": "user", "content": [{"text": prompt[:5000]}]}]},
            "parameters": {"size": settings.wan_image_size, "n": 1, "watermark": settings.wan_image_watermark, "thinking_mode": True},
        }

    @staticmethod
    def _post(api_url: str, api_key: str, payload: dict) -> httpx.Response:
        return httpx.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=settings.wan_image_timeout_seconds,
        )

    def generate(self, prompt: str) -> dict[str, str | bool]:
        api_key = self._api_key()
        if not settings.wan_image_enabled or not api_key:
            raise AppError("WAN_IMAGE_NOT_CONFIGURED", "AI 配图尚未启用。请在服务器 .env 配置 WAN_IMAGE_ENABLED=true 和百炼 Standard API Key。", status_code=503, retryable=True)
        # Model choice deliberately lives only in the server .env.  Neither
        # the browser nor an API request may override it.
        selected_model = settings.wan_image_model.strip()
        if selected_model not in SUPPORTED_WAN_MODELS:
            raise AppError("WAN_IMAGE_MODEL_INVALID", "仅支持 wan2.7-image 或 wan2.7-image-pro。", field="image_model")

        api_url = self._api_url()
        try:
            response = self._post(api_url, api_key, self._payload(selected_model, prompt))
        except httpx.HTTPError as exc:
            raise AppError("WAN_IMAGE_REQUEST_FAILED", "百炼 AI 配图暂时无法连接，请稍后再试。", status_code=503, retryable=True) from exc

        safety_retried = False
        if not response.is_success:
            provider_code, provider_message, request_id = self._provider_failure(response)
            if provider_code == "DataInspectionFailed":
                safety_retried = True
                logger.info("Wan output safety check retried with neutral visual prompt: request_id=%s", request_id or "-")
                try:
                    response = self._post(api_url, api_key, self._payload(selected_model, self._safe_retry_prompt()))
                except httpx.HTTPError as exc:
                    raise AppError("WAN_IMAGE_REQUEST_FAILED", "百炼 AI 配图暂时无法连接，请稍后再试。", status_code=503, retryable=True) from exc
                if response.is_success:
                    provider_code = provider_message = request_id = ""
                else:
                    provider_code, provider_message, request_id = self._provider_failure(response)
            if response.is_success:
                pass
            else:
                logger.warning("Wan image request failed: code=%s request_id=%s", provider_code, request_id or "-")
                raise AppError(
                    "WAN_IMAGE_PROVIDER_ERROR",
                    f"百炼万相未完成出图：{provider_message}",
                    status_code=502,
                    retryable=response.status_code >= 500,
                    suggestion="请核对 Workspace ID、API Key 与地域是否一致，然后重试。",
                    details={"provider_code": provider_code, "request_id": request_id},
                )
        try:
            result = response.json()
        except ValueError as exc:
            raise AppError("WAN_IMAGE_RESPONSE_INVALID", "百炼 AI 配图返回了无法识别的结果。", status_code=502, retryable=True) from exc

        local_url = self._download_to_server(self._extract_image_url(result))
        return {
            "image_url": local_url,
            "image_source": "百炼万相 AI 配图",
            "image_model": selected_model,
            "image_watermarked": bool(settings.wan_image_watermark),
            "image_safety_retry": safety_retried,
            "image_request_id": str(result.get("request_id") or ""),
        }

    @staticmethod
    def _extract_image_url(result: dict) -> str:
        for choice in ((result.get("output") or {}).get("choices") or []):
            for item in ((choice.get("message") or {}).get("content") or []):
                image = item.get("image") if isinstance(item, dict) else None
                if isinstance(image, str) and image.startswith("https://"):
                    return image
        raise AppError("WAN_IMAGE_RESPONSE_INVALID", "百炼 AI 配图没有返回可保存的图片。", status_code=502, retryable=True)

    @staticmethod
    def _safe_output_host(url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host.endswith(suffix) for suffix in _ALLOWED_OUTPUT_HOST_SUFFIXES)

    def _download_to_server(self, url: str) -> str:
        if not self._safe_output_host(url):
            raise AppError("WAN_IMAGE_RESPONSE_INVALID", "百炼 AI 配图返回了不受信任的图片地址。", status_code=502, retryable=True)
        try:
            response = httpx.get(url, timeout=settings.wan_image_timeout_seconds, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise AppError("WAN_IMAGE_DOWNLOAD_FAILED", "AI 配图已生成，但暂时无法保存到服务器。", status_code=502, retryable=True) from exc
        if not response.is_success:
            raise AppError("WAN_IMAGE_DOWNLOAD_FAILED", "AI 配图已生成，但暂时无法保存到服务器。", status_code=502, retryable=True)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise AppError("WAN_IMAGE_RESPONSE_INVALID", "百炼 AI 配图返回了不支持的图片格式。", status_code=502, retryable=True)
        if not response.content or len(response.content) > settings.wan_image_max_bytes:
            raise AppError("WAN_IMAGE_RESPONSE_INVALID", "AI 配图文件大小不符合保存限制。", status_code=502, retryable=True)

        suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[content_type]
        directory = Path(settings.generated_media_dir)
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"wan-{uuid4().hex}{suffix}"
        (directory / filename).write_bytes(response.content)
        return f"{settings.generated_media_url_path.rstrip('/')}/{filename}"
