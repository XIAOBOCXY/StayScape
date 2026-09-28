"""Create one non-demo hotel operator account without seeding demo data.

Usage inside the server container:
  OPERATOR_USERNAME=operations_admin OPERATOR_PASSWORD='...' HOTEL_ID=3 \
    python scripts/create_hotel_user.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "server"))

from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Hotel, User  # noqa: E402


def main() -> None:
    username = os.environ.get("OPERATOR_USERNAME", "").strip()
    password = os.environ.get("OPERATOR_PASSWORD", "")
    hotel_id = int(os.environ.get("HOTEL_ID", "0"))
    if not username or not password or len(password) < 14 or not hotel_id:
        raise SystemExit("OPERATOR_USERNAME, OPERATOR_PASSWORD (14+ chars) and HOTEL_ID are required")
    db = SessionLocal()
    try:
        hotel = db.get(Hotel, hotel_id)
        if not hotel or hotel.status != "ACTIVE":
            raise SystemExit("hotel not found or inactive")
        existing = db.query(User).filter(User.username == username).one_or_none()
        if existing:
            raise SystemExit("username already exists; choose another username")
        db.add(User(username=username, password_hash=hash_password(password), role="HOTEL", hotel_id=hotel_id, status="ACTIVE"))
        db.commit()
        print(f"created hotel operator {username} for hotel {hotel_id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
