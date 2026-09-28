"""Replace every catalog image with a place-matched photo from the web.

For each room type, hotel service and partner experience the script:

1. builds a query from the concrete place (address + name, or room type);
2. asks Baidu image search first and Bing as a fallback, keeping only results
   whose source page mentions part of the query and dropping obvious junk
   (maps, logos, QR codes, watermarks);
3. keeps up to ``MAX_VARIANTS`` distinct photos per room type / service /
   place, rotating them across rows, so different products no longer all show
   the same single image;
4. stores the files locally and writes image_url / source / attribution.

Run inside the server container:  python /app/scripts/refresh_images.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "server"))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import HotelService, PartnerResource, RoomInventory  # noqa: E402
from app.services.media_library_service import MediaLibraryService  # noqa: E402


MAX_VARIANTS = 4

ROOM_KEYWORDS = {
    "大床房": "杭州 精品酒店 大床房 客房",
    "双床房": "杭州 酒店 双床房 客房",
    "湖景大床房": "杭州 西湖 湖景酒店 客房",
    "城市景观房": "杭州 城市景观 酒店 客房",
    "亲子房": "杭州 亲子主题酒店 客房",
    "亲子联通房": "杭州 亲子 连通房 酒店",
    "家庭套房": "杭州 家庭套房 酒店",
    "庭院主题房": "杭州 庭院 主题酒店 客房",
    "影音娱乐房": "杭州 影音娱乐房 酒店 投影",
    "江景大床房": "杭州 钱塘江 江景酒店 客房",
    "露台景观房": "杭州 露台 景观房 酒店",
    "行政套房": "杭州 行政套房 酒店",
    "榻榻米大床房": "杭州 榻榻米 客房 酒店",
    "双卧家庭房": "杭州 双卧 家庭房 酒店",
}


def _room_query(hotel_name: str, room_type: str, features: str) -> str:
    return ROOM_KEYWORDS.get(room_type) or f"杭州 酒店 {room_type} {features[:10]}".strip()


def _service_query(service_name: str) -> str:
    return f"杭州 酒店 {service_name} 实拍"


def _place_query(name: str, address: str) -> str:
    parts = [part.strip() for part in (address, name) if part and str(part).strip()]
    if not parts:
        return "杭州 文旅"
    return " ".join(dict.fromkeys(parts))[:70]


def main() -> None:
    service = MediaLibraryService()
    db = SessionLocal()
    seen_hashes: set[str] = set()
    # key -> list[(candidate_url, stored_image_url)]
    variants: dict[str, list[tuple[str, str]]] = {}
    counters: dict[str, int] = {}
    stats = {"refreshed": 0, "failed": 0, "duplicates": 0, "reused": 0}
    slot = 0

    def assign(record, query: str, key: str) -> bool:
        nonlocal slot
        slot += 1
        pool = variants.setdefault(key, [])
        index = counters.get(key, 0)
        counters[key] = index + 1

        # Already have enough distinct photos for this key: just rotate.
        if pool and (len(pool) >= MAX_VARIANTS or index % 2 == 1):
            record.image_url = pool[index % len(pool)][1]
            record.image_source = "百度/官网检索"
            record.image_attribution = f"关键词「{query}」的公开图片；使用前请核对来源与授权。"
            stats["reused"] += 1
            return True

        candidates = service.search_place_images(query, limit=14)
        if not candidates:
            stats["failed"] += 1
            return False
        for offset in range(len(candidates)):
            url = candidates[(slot + offset) % len(candidates)]
            if any(url == used for used, _ in pool):
                continue
            stored = service.fetch_web_image(url, prefix="place")
            if not stored:
                continue
            path = Path(settings.generated_media_dir) / stored["image_url"].removeprefix(settings.generated_media_url_path).lstrip("/")
            digest = hashlib.sha1(path.read_bytes()).hexdigest() if path.is_file() else ""
            if digest and digest in seen_hashes:
                path.unlink(missing_ok=True)
                stats["duplicates"] += 1
                continue
            if digest:
                seen_hashes.add(digest)
            record.image_url = stored["image_url"]
            record.image_source = "百度/官网检索"
            record.image_attribution = f"关键词「{query}」的公开图片；使用前请核对来源与授权。"
            pool.append((url, stored["image_url"]))
            stats["refreshed"] += 1
            return True

        if pool:
            record.image_url = pool[index % len(pool)][1]
            stats["reused"] += 1
            return True
        stats["failed"] += 1
        return False

    for room in db.scalars(select(RoomInventory)):
        key = f"room:{room.room_type}"
        assign(room, _room_query("", str(room.room_type), str(room.features or "")), key)
        if slot % 10 == 0:
            db.commit()
            print({"progress": slot, **stats}, flush=True)

    for item in db.scalars(select(HotelService)):
        key = f"service:{item.service_name}"
        assign(item, _service_query(str(item.service_name)), key)
        if slot % 10 == 0:
            db.commit()
            print({"progress": slot, **stats}, flush=True)

    for resource in db.scalars(select(PartnerResource)):
        key = f"place:{resource.resource_name}|{resource.address}"
        assign(resource, _place_query(str(resource.resource_name), str(resource.address or "")), key)
        if slot % 10 == 0:
            db.commit()
            print({"progress": slot, **stats}, flush=True)

    db.commit()
    db.close()
    print({"done": True, "keys": len(variants), **stats})


if __name__ == "__main__":
    main()
