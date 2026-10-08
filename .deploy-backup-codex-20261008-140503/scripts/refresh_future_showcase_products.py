"""Refresh unbooked future showcase products with the live itinerary selector."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.showcase_seed import refresh_showcase_itineraries


def main() -> None:
    db = SessionLocal()
    try:
        operator = db.scalar(select(User).where(User.username == "hotel_demo", User.role == "HOTEL"))
        if operator is None or operator.hotel_id is None:
            raise RuntimeError("The hotel_demo operator account is missing or is not linked to a hotel; refusing to refresh an ambiguous tenant.")
        result = refresh_showcase_itineraries(db, int(operator.hotel_id), start_date=date.today())
        db.commit()
        print(result)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
