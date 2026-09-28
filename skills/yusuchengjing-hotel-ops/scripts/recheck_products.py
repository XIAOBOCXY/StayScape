"""Recheck saved portable products after weather or resource facts change."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from calculate_capacity import calculate_capacity
from calculate_finance import calculate_finance
from common import BASE_DIR, data_path, load_json, money, run_cli
from find_substitute import find_substitute
from validate_package import validate_package


def _latest_components(product: dict[str, Any], rooms: dict[str, Any], services: dict[str, Any], partners: dict[str, Any]) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for source in product.get("components") or []:
        item = dict(source)
        source_id = str(item.get("id") or "")
        current = rooms.get(source_id) if item.get("kind") == "ROOM" else services.get(source_id) if item.get("kind") == "HOTEL_SERVICE" else partners.get(source_id)
        if current:
            if item.get("kind") == "ROOM":
                item.update({"remaining": current.get("remaining_inventory"), "unit_cost": current.get("internal_cost"), "status": "AVAILABLE"})
            elif item.get("kind") == "HOTEL_SERVICE":
                item.update({"remaining": current.get("remaining"), "unit_cost": current.get("unit_cost"), "status": "AVAILABLE" if current.get("package_eligible") and int(current.get("remaining") or 0) > 0 else "UNAVAILABLE"})
            else:
                item.update({"remaining": current.get("remaining"), "unit_cost": current.get("settlement_price"), "status": current.get("status"), "approved": current.get("approved"), "weather_tags": current.get("weather_tags"), "min_age": current.get("min_age"), "time_window": (current.get("time_slots") or [""])[0]})
        updated.append(item)
    return updated


def recheck_products(products_data: dict[str, Any], rooms_data: dict[str, Any], services_data: dict[str, Any], resources_data: dict[str, Any], weather_data: dict[str, Any], *, target_date: str | None = None) -> dict[str, Any]:
    rooms = {str(item["room_id"]): item for item in rooms_data.get("rooms") or []}
    services = {str(item["service_id"]): item for item in services_data.get("services") or []}
    partners = {str(item["resource_id"]): item for item in resources_data.get("resources") or []}
    weather = str(weather_data.get("condition") or "")
    affected: list[dict[str, Any]] = []
    for source in products_data.get("products") or []:
        product = dict(source)
        if target_date and product.get("stay_date") != target_date:
            continue
        product["weather"] = weather
        product["components"] = _latest_components(product, rooms, services, partners)
        capacity = calculate_capacity({"components": product["components"]})
        product["capacity"] = capacity
        total_cost = sum((Decimal(str(item.get("unit_cost") or 0)) * Decimal(str(item.get("quantity_per_package") or 0)) for item in product["components"]), Decimal("0"))
        room = rooms.get(str(product.get("room_id"))) or {}
        product["finance"] = calculate_finance({
            "total_cost": total_cost,
            "room_min_sell_price": room.get("min_sell_price"),
            "minimum_margin_rate": "0.25",
            "preferred_price": room.get("normal_price"),
        })
        product["finance"]["minimum_margin_rate"] = 0.25
        validation = validate_package({"product": product})["validation"]
        action = "RECHECKED"
        if validation["status"] != "PASS":
            failed_partner = next((item for item in product["components"] if item.get("kind") == "PARTNER_RESOURCE"), None)
            if failed_partner:
                substitute = find_substitute(resources_data, {
                    "failed_resource_id": failed_partner["id"], "date": product["stay_date"],
                    "target_segment": product["target_segment"], "party_size": failed_partner["quantity_per_package"],
                    "weather": weather, "child_age": product.get("child_age"),
                    "preferred_category": "",
                    "max_settlement_price": failed_partner.get("unit_cost"),
                })
                if substitute.get("candidates"):
                    replacement = substitute["candidates"][0]["resource"]
                    failed_partner.update({
                        "id": replacement["resource_id"], "name": replacement["name"], "remaining": replacement["remaining"],
                        "unit_cost": replacement["settlement_price"], "approved": replacement["approved"], "status": replacement["status"],
                        "weather_tags": replacement["weather_tags"], "min_age": replacement["min_age"], "time_window": replacement["time_slots"][0],
                    })
                    product["capacity"] = calculate_capacity({"components": product["components"]})
                    total_cost = sum((Decimal(str(item.get("unit_cost") or 0)) * Decimal(str(item.get("quantity_per_package") or 0)) for item in product["components"]), Decimal("0"))
                    product["finance"] = calculate_finance({"total_cost": total_cost, "room_min_sell_price": room.get("min_sell_price"), "minimum_margin_rate": "0.25", "preferred_price": room.get("normal_price")})
                    product["finance"]["minimum_margin_rate"] = 0.25
                    validation = validate_package({"product": product})["validation"]
                    action = "REPLACED_RESOURCE" if validation["status"] == "PASS" else "PAUSED"
                else:
                    action = "PAUSED"
            else:
                action = "PAUSED"
        product["validation"] = validation
        product["status"] = "READY_FOR_REVIEW" if validation["status"] == "PASS" else "PAUSED"
        affected.append({"product_id": product.get("product_id"), "status": product["status"], "action": action, "validation": validation, "max_sellable": product["capacity"].get("max_sellable")})
    return {"ok": True, "weather": weather_data, "affected_products": affected}


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="")
    parser.add_argument("--products", default=str(BASE_DIR / "data" / "products.json"))
    args = parser.parse_args()
    return recheck_products(
        load_json(args.products), load_json(data_path("room_inventory.json")), load_json(data_path("hotel_services.json")),
        load_json(data_path("partner_resources.json")), load_json(data_path("weather.json")), target_date=args.date or None,
    )


if __name__ == "__main__":
    run_cli(main)
