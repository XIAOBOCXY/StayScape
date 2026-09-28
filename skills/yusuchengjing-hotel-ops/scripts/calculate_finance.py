"""Calculate margin-safe price floors with Decimal."""

from __future__ import annotations

import argparse
from decimal import Decimal
from typing import Any

from common import as_decimal, money, parse_json_input, rate, run_cli


def calculate_finance(payload: dict[str, Any]) -> dict[str, Any]:
    total_cost = as_decimal(payload.get("total_cost"), "total_cost")
    room_minimum = as_decimal(payload.get("room_min_sell_price"), "room_min_sell_price")
    margin = as_decimal(payload.get("minimum_margin_rate"), "minimum_margin_rate")
    preferred = as_decimal(payload.get("preferred_price"), "preferred_price")
    if total_cost < 0 or room_minimum <= 0 or preferred <= 0 or margin < 0 or margin >= 1:
        raise ValueError("invalid finance input")
    minimum_by_margin = total_cost / (Decimal("1") - margin)
    minimum_valid = max(room_minimum, minimum_by_margin)
    suggested = max(preferred, minimum_valid)
    gross_profit = suggested - total_cost
    gross_margin = gross_profit / suggested
    return {
        "ok": True,
        "total_cost": money(total_cost),
        "minimum_by_margin": money(minimum_by_margin),
        "minimum_valid_price": money(minimum_valid),
        "suggested_price": money(suggested),
        "gross_profit": money(gross_profit),
        "gross_margin_rate": rate(gross_margin),
    }


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="")
    args = parser.parse_args()
    return calculate_finance(parse_json_input(args.input))


if __name__ == "__main__":
    run_cli(main)
