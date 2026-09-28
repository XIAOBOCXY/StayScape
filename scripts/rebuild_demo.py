"""Rebuild the demo dataset and immediately enrich it.

`seed_demo(reset=True)` alone leaves the catalogue without showcase products,
so the reset is followed by a full showcase seed and the enrichment pass
(multi-experience day plans, reviews, confirmed orders, richer copy).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "server"))

from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed import seed_demo  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))

from enrich_demo import enrich_experiences, refresh_copy, seed_orders, seed_reviews  # noqa: E402


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seeded = seed_demo(db, reset=True, include_showcase=True)
        db.commit()
        result = {
            "seeded": seeded,
            "experiences_added": enrich_experiences(db),
            "reviews_created": seed_reviews(db),
            "orders_created": seed_orders(db),
            "products_rewritten": refresh_copy(db),
        }
        db.commit()
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
