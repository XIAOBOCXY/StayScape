from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "server"))

from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed import seed_demo  # noqa: E402


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # A fresh deployment must be immediately demonstrable: seed the same
        # showcase products used by the public H5 instead of only the resource
        # catalog.  ProductService still performs all deterministic capacity,
        # margin and status validation for every showcase plan.
        print(seed_demo(db, reset=False, include_showcase=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
