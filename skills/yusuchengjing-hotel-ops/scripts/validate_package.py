"""The deterministic publish gate for portable 余宿成景 candidates."""

from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
from typing import Any

from common import parse_json_input, weather_matches, windows_overlap, run_cli


def validate_package(payload: dict[str, Any]) -> dict[str, Any]:
    product = payload.get("product") if isinstance(payload.get("product"), dict) else payload
    components = product.get("components")
    errors: list[dict[str, Any]] = []
    required = ("room_id", "target_segment", "weather", "components", "capacity", "finance")
    for field in required:
        if product.get(field) in (None, "", []):
            errors.append({"code": "MISSING_REQUIRED_DATA", "field": field, "message": f"缺少 {field}"})
    if not isinstance(components, list):
        components = []
    if components and not any(item.get("kind") == "ROOM" for item in components):
        errors.append({"code": "MISSING_REQUIRED_DATA", "field": "components", "message": "正式套餐必须包含客房"})
    if components and len(components) < 2:
        errors.append({"code": "MISSING_REQUIRED_DATA", "field": "components", "message": "套餐至少包含客房和一项正式权益"})

    target_weather = str(product.get("weather") or "")
    child_age = product.get("child_age")
    exclusive_windows: list[tuple[str, str]] = []
    for item in components:
        component_id = str(item.get("id") or "")
        kind = str(item.get("kind") or "")
        if kind == "PUBLIC_POI":
            errors.append({"code": "RESOURCE_NOT_APPROVED", "field": "components", "component_id": component_id, "message": "公共 POI 不能作为正式权益"})
            continue
        if kind == "ROOM" and product.get("party_size") is not None and int(item.get("max_guests") or 0) < int(product.get("party_size") or 0):
            errors.append({"code": "CAPACITY_INSUFFICIENT", "field": "party_size", "component_id": component_id, "message": "房型无法容纳套餐同行人数"})
        if kind == "PARTNER_RESOURCE" and not item.get("approved"):
            errors.append({"code": "RESOURCE_NOT_APPROVED", "field": "components", "component_id": component_id, "message": "合作资源未经审核"})
        if item.get("status", "AVAILABLE") != "AVAILABLE":
            errors.append({"code": "RESOURCE_UNAVAILABLE", "field": "components", "component_id": component_id, "message": "正式资源当前不可用"})
        if item.get("remaining") is None or item.get("quantity_per_package") is None:
            errors.append({"code": "MISSING_REQUIRED_DATA", "field": "components", "component_id": component_id, "message": "缺少资源余量或每套消耗量"})
        elif int(item.get("remaining") or 0) < int(item.get("quantity_per_package") or 0):
            errors.append({"code": "CAPACITY_INSUFFICIENT", "field": "components", "component_id": component_id, "message": "资源余量不足以支持一套产品"})
        tags = item.get("weather_tags")
        if target_weather and isinstance(tags, list) and tags and not weather_matches(tags, target_weather):
            errors.append({"code": "WEATHER_MISMATCH", "field": "weather", "component_id": component_id, "message": "资源不适配当前天气"})
        min_age = item.get("min_age")
        max_age = item.get("max_age")
        if child_age is not None and min_age is not None and int(child_age) < int(min_age):
            errors.append({"code": "AGE_NOT_ALLOWED", "field": "child_age", "component_id": component_id, "message": "儿童年龄低于资源要求"})
        if child_age is not None and max_age is not None and int(child_age) > int(max_age):
            errors.append({"code": "AGE_NOT_ALLOWED", "field": "child_age", "component_id": component_id, "message": "儿童年龄高于资源要求"})
        if item.get("exclusive", kind == "PARTNER_RESOURCE") and item.get("time_window"):
            current = str(item["time_window"])
            for prior_window, prior_id in exclusive_windows:
                if windows_overlap(current, prior_window):
                    errors.append({"code": "TIME_CONFLICT", "field": "components", "component_id": component_id, "conflicts_with": prior_id, "message": "正式体验时间冲突"})
                    break
            exclusive_windows.append((current, component_id))

    capacity = product.get("capacity") if isinstance(product.get("capacity"), dict) else {}
    if capacity and int(capacity.get("max_sellable") or 0) <= 0:
        errors.append({"code": "CAPACITY_INSUFFICIENT", "field": "capacity", "message": "组合没有可售数量"})
    finance = product.get("finance") if isinstance(product.get("finance"), dict) else {}
    if finance:
        try:
            actual_margin = Decimal(str(finance.get("gross_margin_rate")))
            minimum_margin = Decimal(str(finance.get("minimum_margin_rate")))
            if actual_margin < minimum_margin:
                errors.append({"code": "MARGIN_TOO_LOW", "field": "finance", "message": "毛利率未达到最低要求"})
        except Exception:
            errors.append({"code": "MISSING_REQUIRED_DATA", "field": "finance", "message": "财务快照不完整"})

    deduplicated: list[dict[str, Any]] = []
    seen = set()
    for item in errors:
        key = (item["code"], item.get("component_id"), item.get("field"))
        if key not in seen:
            seen.add(key)
            deduplicated.append(item)
    status = "PASS" if not deduplicated else "FAIL"
    return {
        "ok": status == "PASS",
        "validation": {
            "status": status,
            "validated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "errors": deduplicated,
            "checked": ["approval", "availability", "capacity", "finance", "time", "weather", "age", "required_data"],
        },
    }


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="")
    args = parser.parse_args()
    return validate_package(parse_json_input(args.input))


if __name__ == "__main__":
    run_cli(main)
