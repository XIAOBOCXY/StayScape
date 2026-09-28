"""Calculate transparent inventory-pressure rankings from room test data."""

from __future__ import annotations

import argparse
from decimal import Decimal
from typing import Any

from common import as_decimal, data_path, load_json, rate, run_cli


def analyze_inventory(data: dict[str, Any], *, stay_date: str | None = None) -> dict[str, Any]:
    actual_date = str(data.get("stay_date") or "")
    if stay_date and actual_date != stay_date:
        return {"ok": True, "stay_date": stay_date, "rooms": [], "priority_room_id": None, "notice": "该日期没有维护测试库存。"}
    rooms = data.get("rooms")
    if not isinstance(rooms, list) or not rooms:
        raise ValueError("room inventory has no rooms")
    results: list[dict[str, Any]] = []
    for row in rooms:
        room_id = str(row.get("room_id") or "")
        total = as_decimal(row.get("total_inventory"), f"{room_id}.total_inventory")
        remaining = as_decimal(row.get("remaining_inventory"), f"{room_id}.remaining_inventory")
        velocity = as_decimal(row.get("recent_sales_velocity"), f"{room_id}.recent_sales_velocity")
        if total <= 0 or remaining < 0 or remaining > total:
            raise ValueError(f"invalid inventory for {room_id}")
        if velocity < 0 or velocity > 1:
            raise ValueError(f"invalid velocity for {room_id}")
        remaining_ratio = remaining / total
        # High remaining stock and low recent velocity both increase pressure.
        pressure = Decimal("0.55") * remaining_ratio + Decimal("0.45") * (Decimal("1") - velocity)
        results.append({
            "room_id": room_id,
            "room_type": row.get("room_type"),
            "remaining_inventory": int(remaining),
            "remaining_ratio": rate(remaining_ratio),
            "recent_sales_velocity": rate(velocity),
            "inventory_pressure": rate(pressure),
        })
    results.sort(key=lambda item: (-item["inventory_pressure"], item["room_id"]))
    for index, item in enumerate(results, start=1):
        item["priority_rank"] = index
    return {
        "ok": True,
        "stay_date": actual_date,
        "formula": "0.55 * remaining_ratio + 0.45 * (1 - recent_sales_velocity)",
        "rooms": results,
        "priority_room_id": results[0]["room_id"],
    }


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(data_path("room_inventory.json")))
    parser.add_argument("--date", default="")
    args = parser.parse_args()
    return analyze_inventory(load_json(args.data), stay_date=args.date or None)


if __name__ == "__main__":
    run_cli(main)
