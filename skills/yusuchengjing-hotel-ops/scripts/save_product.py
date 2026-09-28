"""Persist only PASS candidates to the portable product data file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import BASE_DIR, ToolFailure, load_json, now_iso, parse_json_input, run_cli


def save_product(product: dict[str, Any], products_path: str | Path | None = None) -> dict[str, Any]:
    validation = product.get("validation") if isinstance(product.get("validation"), dict) else {}
    if validation.get("status") != "PASS":
        raise ToolFailure("VALIDATION_NOT_PASS", "只有验证通过的候选可以保存", {"validation_status": validation.get("status")})
    product_id = str(product.get("product_id") or "").strip()
    if not product_id:
        raise ToolFailure("MISSING_REQUIRED_DATA", "缺少 product_id", {"field": "product_id"})
    path = Path(products_path or BASE_DIR / "data" / "products.json")
    existing = load_json(path) if path.exists() else {"data_type": "competition_test_data", "products": []}
    products = list(existing.get("products") or [])
    if any(str(item.get("product_id")) == product_id for item in products):
        raise ToolFailure("PRODUCT_ALREADY_EXISTS", "产品 ID 已存在", {"product_id": product_id})
    stored = dict(product)
    stored["saved_at"] = now_iso()
    products.append(stored)
    existing["products"] = products
    temp_path = path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(existing, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    temp_path.replace(path)
    return {"ok": True, "product_id": product_id, "saved": True, "products_path": str(path)}


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="")
    parser.add_argument("--products", default="")
    args = parser.parse_args()
    return save_product(parse_json_input(args.input), args.products or None)


if __name__ == "__main__":
    run_cli(main)
