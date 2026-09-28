"""Resolve and cache one cover image per resource.

Every room, hotel service and partner experience asks the media library for a
licensed cover that matches its own name and address, then stores the local
URL on the resource.  Cards therefore show different pictures without hitting
a third-party host at render time.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "server"))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import HotelService, PartnerResource, RoomInventory  # noqa: E402
from app.services.media_library_service import MediaLibraryService  # noqa: E402


PREFIX_BY_TYPE = {"ROOM": "客房", "HOTEL_SERVICE": "酒店服务", "PARTNER_RESOURCE": "在地体验"}


def _query(name: str, address: str, kind: str) -> str:
    parts = [part for part in (name, address) if part]
    if kind == "ROOM":
        parts.insert(0, "酒店客房")
    return " ".join(parts)[:120] or "杭州旅行"


def main() -> None:
    db = SessionLocal()
    service = MediaLibraryService()
    resolved = failed = 0
    rows: list[tuple[str, object]] = []
    rows += [("ROOM", item) for item in db.scalars(select(RoomInventory))]
    rows += [("HOTEL_SERVICE", item) for item in db.scalars(select(HotelService))]
    rows += [("PARTNER_RESOURCE", item) for item in db.scalars(select(PartnerResource))]
    for index, (kind, item) in enumerate(rows, start=1):
        if getattr(item, "image_url", ""):
            continue
        name = getattr(item, "room_type", None) or getattr(item, "service_name", None) or getattr(item, "resource_name", "")
        address = getattr(item, "address", "") or ""
        try:
            media = service.automatic_cover(_query(str(name), str(address), kind))
        except Exception:  # noqa: BLE001 - a missing cover must not stop the warm-up
            failed += 1
            continue
        item.image_url = media["image_url"]
        item.image_source = media.get("image_source", "Wikimedia Commons")
        item.image_attribution = media.get("image_attribution", "Wikimedia Commons")
        resolved += 1
        db.flush()
        # Commit as we go: the warm-up can run for several minutes and must not
        # lose finished work if the container restarts.
        if index % 5 == 0:
            db.commit()
            print({"progress": index, "resolved": resolved, "failed": failed}, flush=True)
        time.sleep(0.2)
    db.commit()
    db.close()
    print({"resolved": resolved, "failed": failed})


if __name__ == "__main__":
    main()
