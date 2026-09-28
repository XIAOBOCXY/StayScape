"""Filter approved partner resources and retain exclusion reasons for audit."""

from __future__ import annotations

import argparse
from typing import Any

from common import as_decimal, data_path, load_json, parse_date, parse_json_input, weather_matches, windows_overlap, run_cli


def search_resources(data: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    target_date = parse_date(request.get("date"), "date").isoformat()
    segment = str(request.get("target_segment") or "").strip()
    party_size = int(request.get("party_size") or 0)
    weather = str(request.get("weather") or "").strip()
    child_age = request.get("child_age")
    time_window = str(request.get("time_window") or "").strip()
    if party_size <= 0:
        raise ValueError("party_size must be positive")
    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for resource in data.get("resources") or []:
        reasons: list[str] = []
        resource_id = str(resource.get("resource_id") or "")
        if not resource.get("approved"):
            reasons.append("RESOURCE_NOT_APPROVED")
        if resource.get("status") != "AVAILABLE":
            reasons.append("RESOURCE_UNAVAILABLE")
        if resource.get("date") != target_date:
            reasons.append("DATE_NOT_MATCHED")
        if int(resource.get("remaining") or 0) < party_size:
            reasons.append("CAPACITY_INSUFFICIENT")
        if resource.get("settlement_price") is None:
            reasons.append("MISSING_REQUIRED_DATA")
        if segment and segment not in (resource.get("suitable_segments") or []):
            reasons.append("CROWD_NOT_SUPPORTED")
        if weather and not weather_matches(list(resource.get("weather_tags") or []), weather):
            reasons.append("WEATHER_MISMATCH")
        if child_age is not None and int(child_age) < int(resource.get("min_age") or 0):
            reasons.append("AGE_NOT_ALLOWED")
        slots = list(resource.get("time_slots") or [])
        if time_window and slots and not any(windows_overlap(slot, time_window) for slot in slots):
            reasons.append("TIME_CONFLICT")
        if reasons:
            excluded.append({"resource_id": resource_id, "name": resource.get("name"), "reasons": reasons})
            continue
        accepted.append(dict(resource))
    accepted.sort(key=lambda item: (not bool(item.get("indoor")) if weather in {"小雨", "暴雨"} else False, as_decimal(item.get("settlement_price"), "settlement_price"), str(item.get("resource_id"))))
    return {
        "ok": True,
        "query": {"date": target_date, "target_segment": segment, "party_size": party_size, "weather": weather, "child_age": child_age, "time_window": time_window or None},
        "eligible_resources": accepted,
        "excluded_resources": excluded,
    }


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(data_path("partner_resources.json")))
    parser.add_argument("--input", default="")
    args = parser.parse_args()
    payload = parse_json_input(args.input)
    return search_resources(load_json(args.data), payload)


if __name__ == "__main__":
    run_cli(main)
