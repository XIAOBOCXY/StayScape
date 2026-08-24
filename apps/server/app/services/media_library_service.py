"""Safe storage and licensed public-image discovery for resource cover images."""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from ..config import settings
from ..core.exceptions import AppError


MAX_MEDIA_BYTES = 12 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def _extension(content_type: str) -> str:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized not in ALLOWED_TYPES:
        raise AppError("MEDIA_TYPE_INVALID", "仅支持 JPG、PNG 或 WebP 图片。", field="file")
    return ALLOWED_TYPES[normalized]


def _looks_like_image(content: bytes, content_type: str) -> bool:
    if not content:
        return False
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(content) > 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


class MediaLibraryService:
    """Avoid unlicensed scraping and unsafe hotlinks.

    Merchants can upload their own material.  Without an upload, the service
    searches Wikimedia Commons' public API, downloads the selected thumbnail to
    server-owned storage, and keeps the source attribution with the resource.
    """

    def _directory(self, name: str) -> Path:
        directory = Path(settings.generated_media_dir) / name
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def _public_https(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return False
        host = parsed.hostname
        try:
            addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return False
        for item in addresses:
            address = ipaddress.ip_address(item[4][0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved:
                return False
        return True

    def _write(self, content: bytes, content_type: str, *, prefix: str) -> str:
        suffix = _extension(content_type)
        if len(content) > MAX_MEDIA_BYTES or not _looks_like_image(content, content_type):
            raise AppError("MEDIA_CONTENT_INVALID", "图片文件无效或超过 12MB 限制。", field="file")
        filename = f"{prefix}-{uuid4().hex}{suffix}"
        (self._directory("resource-media") / filename).write_bytes(content)
        return f"{settings.generated_media_url_path.rstrip('/')}/resource-media/{filename}"

    def store_upload(self, content: bytes, content_type: str | None) -> dict[str, str]:
        url = self._write(content, content_type or "", prefix="upload")
        return {"image_url": url, "image_source": "商户上传", "image_attribution": "由商户上传"}

    def search_public(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        clean = " ".join(query.split()).strip()
        if len(clean) < 2:
            raise AppError("MEDIA_QUERY_INVALID", "请输入至少两个字的图片关键词。", field="query")
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrsearch": f"{clean} filetype:bitmap",
            "gsrlimit": max(1, min(int(limit), 12)),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            # Wikimedia's documented standard thumbnail width, not a guessed
            # hotlink URL.  The API can return an equivalent cached size.
            "iiurlwidth": "960",
            "origin": "*",
        }
        try:
            response = httpx.get(COMMONS_API, params=params, timeout=12)
            response.raise_for_status()
            pages = (response.json().get("query") or {}).get("pages") or []
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError("MEDIA_SEARCH_UNAVAILABLE", "暂时无法查找网络图片，请上传自己的图片或稍后再试。", status_code=503, retryable=True) from exc
        results: list[dict[str, str]] = []
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            thumb = str(info.get("thumburl") or info.get("url") or "")
            if not self._public_https(thumb):
                continue
            metadata = info.get("extmetadata") or {}
            license_name = str((metadata.get("LicenseShortName") or {}).get("value") or "")
            artist = str((metadata.get("Artist") or {}).get("value") or "")
            title = str(page.get("title") or "网络图片").removeprefix("File:")
            detail_url = str(info.get("descriptionurl") or "https://commons.wikimedia.org")
            results.append(
                {
                    "title": title,
                    "preview_url": thumb,
                    "source_url": thumb,
                    "source": "Wikimedia Commons",
                    "attribution": " · ".join(part for part in (license_name, artist) if part) or "Wikimedia Commons",
                    "detail_url": detail_url,
                }
            )
        return results

    def import_remote(self, url: str, *, source: str = "网络图片", attribution: str = "") -> dict[str, str]:
        if not self._public_https(url):
            raise AppError("MEDIA_URL_UNSAFE", "网络图片地址必须是可公开访问的 HTTPS 图片地址。", field="url")
        try:
            response = httpx.get(url, timeout=20, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise AppError("MEDIA_IMPORT_UNAVAILABLE", "网络图片暂时无法下载，请换一张或直接上传。", status_code=503, retryable=True) from exc
        if not response.is_success:
            raise AppError("MEDIA_IMPORT_UNAVAILABLE", "网络图片暂时无法下载，请换一张或直接上传。", status_code=502, retryable=True)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        local_url = self._write(response.content, content_type, prefix="web")
        return {"image_url": local_url, "image_source": source[:120] or "网络图片", "image_attribution": attribution[:500]}

    def automatic_cover(self, query: str) -> dict[str, str]:
        key = hashlib.sha256(" ".join(query.lower().split()).encode("utf-8")).hexdigest()[:20]
        cached = next(self._directory("resource-media").glob(f"auto-{key}.*"), None)
        if cached:
            return {"image_url": f"{settings.generated_media_url_path.rstrip('/')}/resource-media/{cached.name}", "image_source": "Wikimedia Commons", "image_attribution": "Wikimedia Commons"}
        candidates = self.search_public(query, limit=8)
        if not candidates:
            raise AppError("MEDIA_SEARCH_EMPTY", "暂未找到合适的网络图片，请上传自己的图片。", status_code=404)
        # Different resources with the same broad category should not all
        # inherit the first search result.  The stable hash keeps a resource's
        # cover consistent after refresh while distributing choices across the
        # licensed result set.
        selected = candidates[int(key, 16) % len(candidates)]
        imported = self.import_remote(selected["source_url"], source=selected["source"], attribution=selected["attribution"])
        source_path = Path(settings.generated_media_dir) / imported["image_url"].removeprefix(settings.generated_media_url_path).lstrip("/")
        target = source_path.with_name(f"auto-{key}{source_path.suffix}")
        if source_path.exists() and not target.exists():
            source_path.replace(target)
            imported["image_url"] = f"{settings.generated_media_url_path.rstrip('/')}/resource-media/{target.name}"
        return imported
