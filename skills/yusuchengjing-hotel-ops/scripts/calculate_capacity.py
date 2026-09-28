"""Calculate the strict package bottleneck from formal components only."""

from __future__ import annotations

import argparse
from typing import Any

from common import data_path, load_json, parse_json_input, run_cli


def calculate_capacity(payload: dict[str, Any]) -> dict[str, Any]:
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("components is required")
    rows: list[dict[str, Any]] = []
    for component in components:
        component_id = str(component.get("id") or "")
        if component.get("kind") == "PUBLIC_POI":
            continue
        if not component.get("approved", True):
            return {"ok": False, "error_code": "RESOURCE_NOT_APPROVED", "message": "未审核资源不能参与套餐容量", "details": {"component_id": component_id}}
        remaining = component.get("remaining")
        quantity = component.get("quantity_per_package")
        if remaining is None or quantity is None:
            return {"ok": False, "error_code": "MISSING_REQUIRED_DATA", "message": "容量计算缺少资源余量或每套消耗量", "details": {"component_id": component_id}}
        remaining, quantity = int(remaining), int(quantity)
        if remaining < 0 or quantity <= 0:
            return {"ok": False, "error_code": "MISSING_REQUIRED_DATA", "message": "容量字段无效", "details": {"component_id": component_id}}
        rows.append({"id": component_id, "name": component.get("name") or component_id, "kind": component.get("kind") or "RESOURCE", "remaining": remaining, "quantity_per_package": quantity, "supported_packages": remaining // quantity})
    if not rows:
        return {"ok": False, "error_code": "MISSING_REQUIRED_DATA", "message": "没有正式权益可计算容量", "details": {}}
    rows.sort(key=lambda item: (item["supported_packages"], item["id"]))
    bottleneck = rows[0]
    return {"ok": True, "components": rows, "max_sellable": bottleneck["supported_packages"], "bottleneck_resource": {"id": bottleneck["id"], "name": bottleneck["name"], "supported_packages": bottleneck["supported_packages"]}}


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="")
    args = parser.parse_args()
    return calculate_capacity(parse_json_input(args.input))


if __name__ == "__main__":
    run_cli(main)
