"""Safe storage and licensed public-image discovery for resource cover images."""

from __future__ import annotations

import hashlib
import ipaddress
import re
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
# Public image hosts the storefront may reference.  Everything is copied onto
# our own storage once and then served from there, so a page never waits for a
# third-party CDN on every render.
PROXY_HOSTS = {
    "images.unsplash.com",
    "images.pexels.com",
    "commons.wikimedia.org",
    "upload.wikimedia.org",
}

# Search engines that answer a plain keyword request from the deployment host.
# Results are downloaded once and served from local storage, so a page never
# depends on the search host or the original image host at render time.
WEB_SEARCH_URL = "https://www.bing.com/images/async"
WEB_SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
IMAGE_URL_PATTERN = re.compile(r'murl&quot;:&quot;(https?://[^&]+?)&quot;')

# 关键词命中也要排除这些明显无关的结果：地图、图标、二维码、水印、广告位等。
IRRELEVANT_URL_TOKENS = (
    "map", "ditu", "staticmap", "tile", "logo", "icon", "qrcode", "erweima",
    "watermark", "shuiyin", "sprite", "placeholder", "loading", "avatar",
)
IRRELEVANT_TEXT_TOKENS = ("地图", "logo", "图标", "二维码", "水印", "广告", "logo图")
BLOCKED_IMAGE_HOSTS = ("map.baidu.com", "maps.google", "staticmap", "tile.openstreetmap")

# 提到「乐园」时，别把别的乐园的图当成杭州乐园的图。
OTHER_PARK_TOKENS = (
    "hello kitty", "hellokitty", "凯蒂猫", "迪士尼", "disney", "环球影城", "universal",
    "方特", "长隆", "欢乐谷", "嬉戏谷", "world joyland",
)


def _looks_irrelevant(image_url: str, context: str = "") -> bool:
    """True when a search hit is obviously not a usable place/room photo."""

    lowered = image_url.lower()
    if any(host in lowered for host in BLOCKED_IMAGE_HOSTS):
        return True
    stem = lowered.split("?")[0]
    if any(token in stem for token in IRRELEVANT_URL_TOKENS):
        return True
    text = str(context or "").lower()
    if any(token in text for token in IRRELEVANT_TEXT_TOKENS):
        return True
    return False


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


def _detected_content_type(content: bytes, declared: str) -> str:
    """Normalise a CDN's generic MIME header from the actual image signature."""
    normalized = declared.split(";", 1)[0].strip().lower()
    for content_type in ALLOWED_TYPES:
        if _looks_like_image(content, content_type):
            return content_type
    return normalized


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
        content_type = _detected_content_type(content, content_type)
        suffix = _extension(content_type)
        if len(content) > MAX_MEDIA_BYTES or not _looks_like_image(content, content_type):
            raise AppError("MEDIA_CONTENT_INVALID", "图片文件无效或超过 12MB 限制。", field="file")
        filename = f"{prefix}-{uuid4().hex}{suffix}"
        (self._directory("resource-media") / filename).write_bytes(content)
        return f"{settings.generated_media_url_path.rstrip('/')}/resource-media/{filename}"

    def store_upload(self, content: bytes, content_type: str | None) -> dict[str, str]:
        url = self._write(content, content_type or "", prefix="upload")
        return {"image_url": url, "image_source": "商户上传", "image_attribution": "由商户上传"}

    def search_public(self, query: str, limit: int = 8, *, prefetch: bool = False) -> list[dict[str, str]]:
        """Place-relevant public images for the operator picker.

        Sources are the ones that actually answer from the deployment host:
        Baidu image search first, then a Bing fallback.  When ``prefetch`` is
        set (the workbench picker) each hit is copied to local storage so the
        thumbnail renders without hot-linking a third-party CDN.
        """

        clean = " ".join(query.split()).strip()
        if len(clean) < 2:
            raise AppError("MEDIA_QUERY_INVALID", "请输入至少两个字的图片关键词。", field="query")
        candidates = [url for url in self.search_place_images(clean, limit=max(limit, 6)) if not _looks_irrelevant(url)]
        if not candidates:
            raise AppError(
                "MEDIA_SEARCH_UNAVAILABLE",
                "暂时没抓到合适的公开图片：可以换成更具体的「地点 + 名称」关键词（例如「杭州 拱宸桥 运河夜游」），或直接上传自己的图片。",
                status_code=503,
                retryable=True,
            )
        results: list[dict[str, str]] = []
        for url in candidates:
            source_name = "百度图片" if "baidu" in url.lower() else "公开图片"
            attribution = f"关键词「{clean}」检索到的公开图片；正式使用前请点开来源核对授权。"
            item: dict[str, str] = {
                "title": clean,
                "preview_url": url,
                "source_url": url,
                "source": source_name,
                "attribution": attribution,
                "detail_url": url,
            }
            if prefetch:
                downloaded = self.fetch_web_image(url, prefix="pick")
                if not downloaded:
                    continue
                # Preview from our own storage so the picker never hot-links a
                # third-party CDN, and reuse it directly if the operator picks it.
                item["preview_url"] = downloaded["image_url"]
                item["image_url"] = downloaded["image_url"]
            results.append(item)
            if len(results) >= limit:
                break
        if not results:
            raise AppError("MEDIA_SEARCH_UNAVAILABLE", "抓到的图片暂时无法下载，请换一张或直接上传。", status_code=503, retryable=True)
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
        content_type = _detected_content_type(response.content, response.headers.get("content-type", ""))
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

    def proxy_remote(self, url: str) -> dict[str, str]:
        """Download a known public image once and serve it from local storage."""

        host = (urlparse(url).hostname or "").lower()
        if host not in PROXY_HOSTS or not self._public_https(url):
            raise AppError("MEDIA_URL_UNSAFE", "该图片地址不在允许的来源列表中。", field="url")
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        cached = next(self._directory("resource-media").glob(f"proxy-{key}.*"), None)
        if cached:
            return {
                "image_url": f"{settings.generated_media_url_path.rstrip('/')}/resource-media/{cached.name}",
                "image_source": host,
                "image_attribution": host,
            }
        try:
            # The host was checked before the request. Do not follow an
            # unchecked redirect into a private network or an unbounded URL.
            response = httpx.get(url, timeout=25, follow_redirects=False)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError("MEDIA_IMPORT_UNAVAILABLE", "图片暂时无法下载。", status_code=503, retryable=True) from exc
        content_type = _detected_content_type(response.content, response.headers.get("content-type", ""))
        stored = self._write(response.content, content_type, prefix="proxy")
        source_path = Path(settings.generated_media_dir) / stored["image_url"].removeprefix(settings.generated_media_url_path).lstrip("/")
        target = source_path.with_name(f"proxy-{key}{source_path.suffix}")
        if source_path.exists() and not target.exists():
            source_path.replace(target)
            stored["image_url"] = f"{settings.generated_media_url_path.rstrip('/')}/resource-media/{target.name}"
        stored["image_source"] = host
        stored["image_attribution"] = host
        return stored

    def search_web_images(self, query: str, limit: int = 12) -> list[str]:
        """Keyword image search that works from the deployment host.

        Returns the original image URLs so the caller can download and store a
        copy locally; nothing is hot-linked from the results page.
        """

        clean = " ".join(str(query or "").split())[:80]
        if len(clean) < 2:
            return []
        try:
            response = httpx.get(
                WEB_SEARCH_URL,
                params={"q": clean, "first": 1, "count": max(10, min(int(limit) * 3, 35)), "mmasync": 1},
                headers=WEB_SEARCH_HEADERS,
                timeout=15,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        urls: list[str] = []
        # Pair each image with the page it came from so results can be checked
        # against the requested place instead of accepting any random photo.
        pairs = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;.*?purl&quot;:&quot;(https?://[^&]+?)&quot;', response.text)
        grammar = {clean[index:index + 2] for index in range(max(0, len(clean) - 1))}
        relevant: list[str] = []
        for image_url, page_url in pairs:
            image_url = html_like_unescape(image_url)
            page_url = html_like_unescape(page_url)
            if not image_url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            if image_url in urls:
                continue
            urls.append(image_url)
            if any(token and token in page_url for token in grammar):
                relevant.append(image_url)
        if relevant:
            return relevant[:limit]
        for match in IMAGE_URL_PATTERN.findall(response.text):
            url = html_like_unescape(match)
            if url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")) and url not in urls:
                urls.append(url)
            if len(urls) >= limit:
                break
        return urls

    def search_place_images(self, query: str, limit: int = 12) -> list[str]:
        """Place-matched images from Baidu first, then Bing.

        Baidu is preferred because it is reachable from the deployment host and
        indexes official/scenic-area photos; Bing stays as a fallback.  Both
        paths keep only results whose source page mentions part of the query, so
        an unrelated picture is never attached to a room or an experience.
        """

        clean = " ".join(str(query or "").split())[:80]
        if len(clean) < 2:
            return []
        baidu = self._search_baidu(clean, limit)
        if baidu:
            return baidu
        return self.search_web_images(clean, limit)

    def _search_baidu(self, query: str, limit: int) -> list[str]:
        headers = {
            **WEB_SEARCH_HEADERS,
            "Referer": "https://image.baidu.com/",
            "Accept": "application/json, text/plain, */*",
        }
        params = {
            "tn": "resultjson_com",
            "ipn": "rj",
            "ct": "201326592",
            "is": "",
            "fp": "result",
            "word": query,
            "queryWord": query,
            "cl": "2",
            "lm": "-1",
            "ie": "utf-8",
            "oe": "utf-8",
            "pn": "0",
            "rn": str(max(10, min(limit * 3, 30))),
        }
        try:
            response = httpx.get(
                "https://image.baidu.com/search/acjson",
                params=params,
                headers=headers,
                timeout=15,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        grammar = {query[index:index + 2] for index in range(max(0, len(query) - 1))}
        results: list[str] = []
        for row in payload.get("data") or []:
            if not isinstance(row, dict):
                continue
            image_url = str(row.get("thumbURL") or row.get("middleURL") or "")
            if not image_url.startswith("https://"):
                continue
            if _looks_irrelevant(image_url, " ".join(str(row.get(key) or "") for key in ("fromPageTitleEnc", "fromURL", "fromURLHost"))):
                continue
            context = " ".join(
                str(row.get(key) or "")
                for key in ("fromPageTitleEnc", "fromURL", "fromURLHost", "replaceUrl")
            )
            lowered_query = query.lower()
            if any(token in context.lower() for token in OTHER_PARK_TOKENS) and not any(
                token in lowered_query for token in OTHER_PARK_TOKENS
            ):
                continue
            if not any(token and token in context for token in grammar):
                continue
            if image_url not in results:
                results.append(image_url)
            if len(results) >= limit:
                break
        return results

    def fetch_web_image(self, url: str, *, prefix: str = "web") -> dict[str, str] | None:
        """Download one search result into local storage (best effort)."""

        try:
            response = httpx.get(url, headers=WEB_SEARCH_HEADERS, timeout=20, follow_redirects=True)
            response.raise_for_status()
            content_type = _detected_content_type(response.content, response.headers.get("content-type", ""))
            image_url = self._write(response.content, content_type, prefix=prefix)
        except (httpx.HTTPError, AppError):
            return None
        return {
            "image_url": image_url,
            "image_source": urlparse(url).hostname or "网络图片",
            "image_attribution": url[:480],
        }


def html_like_unescape(value: str) -> str:
    return (
        value.replace("&amp;", "&")
        .replace("&#47;", "/")
        .replace("&quot;", '"')
        .replace("\\/", "/")
    )
