"""Download the curated storefront images onto our own server.

Third-party image hosts (Wikimedia, Pexels) are unreachable or slow from the
deployment host, so every catalog image is copied once into
`generated_media/resource-media` and served from `/generated-media/...`.
Keys whose remote file cannot be fetched reuse another local image of the same
kind, so a card never points at an external host.
"""

from __future__ import annotations

import re
import shutil
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "server"))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402


MEDIA_SOURCE = ROOT / "apps" / "web" / "src" / "utils" / "productMedia.ts"
ENTRY = re.compile(r"(\w+):\s*\{\s*id:\s*'[^']+',\s*url:\s*'(https://[^']+)'[^}]*?kind:\s*'([^']+)'")
TARGET_DIR = Path(settings.generated_media_dir) / "resource-media"


def _extension(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    return {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(content_type, ".jpg")


def main() -> None:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    list_path = os.environ.get("MEDIA_LIST_FILE", "/tmp/media_list.json")
    if Path(list_path).is_file():
        # The web sources are not part of the server image, so the image list is
        # handed over as JSON instead of being parsed at runtime.
        entries = [(row["key"], row["url"], row["kind"]) for row in json.loads(Path(list_path).read_text(encoding="utf-8"))]
    else:
        entries = ENTRY.findall(MEDIA_SOURCE.read_text(encoding="utf-8"))
    if not entries:
        raise SystemExit("no catalog entries found")

    downloaded: dict[str, Path] = {}
    by_kind: dict[str, Path] = {}
    failed: list[str] = []
    for key, url, kind in entries:
        existing = next(TARGET_DIR.glob(f"curated-{key}.*"), None)
        if existing:
            downloaded[key] = existing
            by_kind.setdefault(kind, existing)
            continue
        try:
            response = httpx.get(url, timeout=20, follow_redirects=True)
            response.raise_for_status()
        except Exception:  # noqa: BLE001 - unreachable hosts fall back to a local copy
            failed.append(key)
            continue
        target = TARGET_DIR / f"curated-{key}{_extension(response)}"
        target.write_bytes(response.content)
        downloaded[key] = target
        by_kind.setdefault(kind, target)
        print({"saved": key, "bytes": len(response.content)}, flush=True)

    fallback = next(iter(downloaded.values()), None)
    for key, url, kind in entries:
        if key in downloaded:
            continue
        donor = by_kind.get(kind) or fallback
        if donor is None:
            continue
        target = donor.with_name(f"curated-{key}{donor.suffix}")
        if not target.exists():
            shutil.copyfile(donor, target)
        downloaded[key] = target
    print({"downloaded": len(downloaded), "from_remote": len(entries) - len(failed), "copied_locally": len(failed), "failed": failed[:10]})


if __name__ == "__main__":
    main()
