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
        print(seed_demo(db, reset=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()

