"""Re-fetch only the theme-park partner images with the stricter filter."""
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import PartnerResource
from app.services.media_library_service import MediaLibraryService


def main() -> int:
    service = MediaLibraryService()
    db = SessionLocal()
    rows = list(db.scalars(select(PartnerResource).where(PartnerResource.resource_name.contains("乐园"))).all())
    print("park resources:", len(rows))
    changed = 0
    for row in rows:
        query = f"{row.address or '杭州'} {row.resource_name} 实景"
        for url in service.search_place_images(query, limit=10):
            stored = service.fetch_web_image(url, prefix="place")
            if not stored:
                continue
            row.image_url = stored["image_url"]
            row.image_source = "百度/官网检索"
            row.image_attribution = f"关键词「{query}」的公开图片；使用前请核对来源与授权。"
            changed += 1
            break
    db.commit()
    db.close()
    print("updated:", changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
