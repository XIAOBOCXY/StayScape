"""Calculate explainable segment demand scores from aggregate sales data."""

from __future__ import annotations

import argparse
from decimal import Decimal
from typing import Any

from common import as_decimal, data_path, load_json, rate, run_cli


def _fraction(numerator: Decimal, denominator: Decimal) -> Decimal:
    return numerator / denominator if denominator > 0 else Decimal("0")


def analyze_demand(data: dict[str, Any]) -> dict[str, Any]:
    segments = data.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("recent sales has no segments")
    rows: list[dict[str, Any]] = []
    for source in segments:
        name = str(source.get("segment") or "")
        views = as_decimal(source.get("views"), f"{name}.views")
        inquiries = as_decimal(source.get("inquiries"), f"{name}.inquiries")
        intentions = as_decimal(source.get("intentions"), f"{name}.intentions")
        bookings = as_decimal(source.get("bookings"), f"{name}.bookings")
        if min(views, inquiries, intentions, bookings) < 0 or inquiries > views or intentions > inquiries or bookings > intentions:
            raise ValueError(f"invalid funnel for {name}")
        inquiry_rate = _fraction(inquiries, views)
        intention_rate = _fraction(intentions, inquiries)
        booking_rate = _fraction(bookings, intentions)
        # A documented, intentionally simple weighted funnel score.
        score = Decimal("0.25") * inquiry_rate + Decimal("0.35") * intention_rate + Decimal("0.40") * booking_rate
        rows.append({
            "segment": name,
            "views": int(views),
            "inquiries": int(inquiries),
            "intentions": int(intentions),
            "bookings": int(bookings),
            "inquiry_rate": rate(inquiry_rate),
            "intention_rate": rate(intention_rate),
            "booking_rate": rate(booking_rate),
            "demand_score": rate(score),
        })
    rows.sort(key=lambda item: (-item["demand_score"], item["segment"]))
    return {
        "ok": True,
        "period_days": data.get("period_days"),
        "formula": "0.25 * inquiry_rate + 0.35 * intention_rate + 0.40 * booking_rate",
        "segments": rows,
        "priority_segment": rows[0]["segment"],
    }


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(data_path("recent_sales.json")))
    args = parser.parse_args()
    return analyze_demand(load_json(args.data))


if __name__ == "__main__":
    run_cli(main)
