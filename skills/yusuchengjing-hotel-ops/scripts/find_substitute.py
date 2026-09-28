"""Find compatible approved substitutes without changing a product itself."""

from __future__ import annotations

import argparse
from typing import Any

from common import as_decimal, data_path, load_json, parse_json_input, weather_matches, run_cli


def find_substitute(data: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    excluded_id = str(request.get("failed_resource_id") or "")
    target_date = str(request.get("date") or "")
    segment = str(request.get("target_segment") or "")
    party_size = int(request.get("party_size") or 0)
    weather = str(request.get("weather") or "")
    child_age = request.get("child_age")
    category = str(request.get("preferred_category") or "")
    max_cost = as_decimal(request.get("max_settlement_price"), "max_settlement_price") if request.get("max_settlement_price") is not None else None
    if not target_date or party_size <= 0:
        raise ValueError("date and party_size are required")
    candidates: list[dict[str, Any]] = []
    for resource in data.get("resources") or []:
        if str(resource.get("resource_id")) == excluded_id:
            continue
        if not resource.get("approved") or resource.get("status") != "AVAILABLE" or resource.get("date") != target_date:
            continue
        if int(resource.get("remaining") or 0) < party_size:
            continue
        if segment and segment not in (resource.get("suitable_segments") or []):
            continue
        if weather and not weather_matches(list(resource.get("weather_tags") or []), weather):
            continue
        if child_age is not None and int(child_age) < int(resource.get("min_age") or 0):
            continue
        cost = as_decimal(resource.get("settlement_price"), "settlement_price")
        if max_cost is not None and cost > max_cost:
            continue
        score = 0
        if category and resource.get("category") == category:
            score += 5
        if weather in {"小雨", "暴雨"} and resource.get("indoor"):
            score += 3
        score += min(3, int(resource.get("remaining") or 0) // max(1, party_size))
        candidates.append({"resource": dict(resource), "fit_score": score, "settlement_price": str(cost)})
    candidates.sort(key=lambda item: (-item["fit_score"], as_decimal(item["settlement_price"], "settlement_price"), str(item["resource"].get("resource_id"))))
    return {"ok": True, "failed_resource_id": excluded_id, "candidates": candidates}


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(data_path("partner_resources.json")))
    parser.add_argument("--input", default="")
    args = parser.parse_args()
    return find_substitute(load_json(args.data), parse_json_input(args.input))


if __name__ == "__main__":
    run_cli(main)
