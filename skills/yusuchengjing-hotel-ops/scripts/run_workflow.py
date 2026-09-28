"""Run a complete, local deterministic 余宿成景 demonstration workflow."""

from __future__ import annotations

import argparse
from decimal import Decimal
from typing import Any

from analyze_demand import analyze_demand
from analyze_inventory import analyze_inventory
from calculate_capacity import calculate_capacity
from calculate_finance import calculate_finance
from common import data_path, load_json, money, run_cli
from save_product import save_product
from search_resources import search_resources
from validate_package import validate_package


PARTY_SIZE = {
    "情侣/双人客": 2,
    "亲子家庭": 3,
    "年轻朋友结伴": 2,
    "本地周末微度假": 2,
}


def _room_component(room: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": room["room_id"],
        "name": room["room_type"],
        "kind": "ROOM",
        "remaining": room["remaining_inventory"],
        "quantity_per_package": 1,
        "approved": True,
        "status": "AVAILABLE",
        "exclusive": False,
        "unit_cost": room["internal_cost"],
        "max_guests": room["max_guests"],
    }


def _service_components(services: list[dict[str, Any]], segment: str, party_size: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    breakfast = next((item for item in services if item.get("service_id") == "HS001"), None)
    child_breakfast = next((item for item in services if item.get("service_id") == "HS003"), None)
    late_checkout = next((item for item in services if item.get("service_id") == "HS002"), None)
    if breakfast and breakfast.get("package_eligible"):
        selected.append({
            "id": breakfast["service_id"], "name": breakfast["name"], "kind": "HOTEL_SERVICE",
            "remaining": breakfast["remaining"], "quantity_per_package": 2 if segment == "亲子家庭" else party_size,
            "approved": True, "status": "AVAILABLE", "exclusive": False, "time_window": breakfast["available_window"],
            "unit_cost": breakfast["unit_cost"],
        })
    if segment == "亲子家庭" and child_breakfast and child_breakfast.get("package_eligible"):
        selected.append({
            "id": child_breakfast["service_id"], "name": child_breakfast["name"], "kind": "HOTEL_SERVICE",
            "remaining": child_breakfast["remaining"], "quantity_per_package": 1,
            "approved": True, "status": "AVAILABLE", "exclusive": False, "time_window": child_breakfast["available_window"],
            "unit_cost": child_breakfast["unit_cost"],
        })
    if late_checkout and late_checkout.get("package_eligible"):
        selected.append({
            "id": late_checkout["service_id"], "name": late_checkout["name"], "kind": "HOTEL_SERVICE",
            "remaining": late_checkout["remaining"], "quantity_per_package": 1,
            "approved": True, "status": "AVAILABLE", "exclusive": False, "time_window": late_checkout["available_window"],
            "unit_cost": late_checkout["unit_cost"],
        })
    return selected


def _partner_component(resource: dict[str, Any], party_size: int) -> dict[str, Any]:
    return {
        "id": resource["resource_id"], "name": resource["name"], "kind": "PARTNER_RESOURCE",
        "remaining": resource["remaining"], "quantity_per_package": party_size,
        "approved": resource["approved"], "status": resource["status"], "exclusive": True,
        "time_window": (resource.get("time_slots") or [""])[0],
        "weather_tags": resource.get("weather_tags") or [], "min_age": resource.get("min_age"),
        "suitable_segments": resource.get("suitable_segments") or [], "unit_cost": resource["settlement_price"],
        "reservation_required": resource.get("reservation_required"), "cancel_rule": resource.get("cancel_rule"),
    }


def _route(knowledge: dict[str, Any], segment: str, rainy: bool) -> list[dict[str, Any]]:
    score_key = "parent_child_score" if segment == "亲子家庭" else "couple_score" if segment == "情侣/双人客" else "couple_score"
    ranked = sorted(
        knowledge.get("pois") or [],
        key=lambda item: (
            -int(item.get("rainy_day_score") or 0) if rainy else 0,
            -int(item.get(score_key) or 0),
            int(item.get("walking_intensity") or 9),
            str(item.get("poi_id")),
        ),
    )
    item = ranked[0] if ranked else None
    if not item:
        return []
    return [{
        "kind": "PUBLIC_ROUTE_SUGGESTION",
        "name": item["name"],
        "recommended_duration_min": item["recommended_duration_min"],
        "source_name": item["source_name"],
        "source_url": item["source_url"],
        "verification_status": item["verification_status"],
        "notice": "公共路线建议，不含在套餐权益中；信息需以来源页面最新公告为准。",
    }]


def _marketing(product: dict[str, Any], partner: dict[str, Any], room: dict[str, Any], components: list[dict[str, Any]]) -> dict[str, Any]:
    inclusion_names = [item["name"] for item in components if item["kind"] != "ROOM"]
    time_slot = (partner.get("time_slots") or ["具体时段以确认信息为准"])[0]
    inclusions = "、".join(inclusion_names)
    price = product["finance"]["suggested_price"]
    return {
        "h5": f"{product['stay_date']}入住，住进{room['room_type']}一晚；{time_slot}安排{partner['name']}。正式权益含{inclusions}，请按确认信息到店与预约。",
        "moments": f"周末把行程留一点空白：{time_slot}去{partner['name']}，第二天{inclusion_names[-1] if inclusion_names else '按酒店确认安排'}。{product['name']}，¥{price}起。",
        "xiaohongshu": {
            "title": product["name"],
            "content": f"这次不赶景点。下午到店放行李，{time_slot}去{partner['name']}；晚上按自己的节奏吃饭散步。第二天有{inclusions}，住一晚的时间刚好够用。"
        },
        "video_30s": [
            {"seconds": "0-3", "shot": f"房卡与{room['room_type']}门口的安静一秒"},
            {"seconds": "3-12", "shot": f"{time_slot}，{partner['name']}的真实动作细节"},
            {"seconds": "12-24", "shot": "晚间留白，不虚构未包含的餐饮或景点"},
            {"seconds": "24-30", "shot": f"次日{inclusions}，展示验证后的预约 CTA"}
        ],
        "poster_brief": {
            "image_layer": f"围绕{partner['name']}的真实体验动作，保留左下文字安全区；不生成文字、Logo、票券或未确认设施。",
            "text_layer": ["产品名", "一行副标题", "正式权益", f"¥{price}起", f"最多{product['capacity']['max_sellable']}套", "立即咨询"]
        },
        "poster_prompt": f"Editorial vertical travel product hero, Hangzhou test-hotel weekend, focus on {partner['name']} activity at {time_slot}, audience {product['target_segment']}, factual room cue {room['room_type']}, natural light, tactile details, left lower third clear for separately rendered text, no words, no logos, no price, no QR code, no invented landmark, no unverified facility."
    }


def generate_products(*, target_date: str, count: int, save: bool = False) -> dict[str, Any]:
    rooms_data = load_json(data_path("room_inventory.json"))
    services_data = load_json(data_path("hotel_services.json"))
    sales_data = load_json(data_path("recent_sales.json"))
    resources_data = load_json(data_path("partner_resources.json"))
    weather_data = load_json(data_path("weather.json"))
    knowledge_data = load_json(data_path("tourism_knowledge.json"))
    inventory = analyze_inventory(rooms_data, stay_date=target_date)
    demand = analyze_demand(sales_data)
    weather = str(weather_data.get("condition") or "")
    room_by_id = {str(item["room_id"]): item for item in rooms_data.get("rooms") or []}
    priority_room = room_by_id.get(str(inventory.get("priority_room_id")))
    if not priority_room:
        return {"ok": False, "error_code": "MISSING_REQUIRED_DATA", "message": "没有可用临期房型", "details": {}}
    candidates: list[dict[str, Any]] = []
    pressure_by_room = {str(item["room_id"]): float(item["inventory_pressure"]) for item in inventory.get("rooms") or []}
    for index, demand_row in enumerate((demand.get("segments") or [])[: max(1, count)]):
        segment = demand_row["segment"]
        party_size = PARTY_SIZE.get(segment, 2)
        compatible_rooms = [room for room in room_by_id.values() if int(room.get("max_guests") or 0) >= party_size and int(room.get("remaining_inventory") or 0) > 0]
        compatible_rooms.sort(key=lambda room: (-pressure_by_room.get(str(room["room_id"]), -1), str(room["room_id"])))
        room = compatible_rooms[0] if compatible_rooms else None
        if not room:
            candidates.append({"status": "SKIPPED", "target_segment": segment, "reason": "没有可容纳该同行人数的临期房型。"})
            continue
        resources = search_resources(resources_data, {
            "date": target_date, "target_segment": segment, "party_size": party_size,
            "weather": weather, "child_age": 6 if segment == "亲子家庭" else None,
        })
        eligible = resources.get("eligible_resources") or []
        if not eligible:
            candidates.append({"status": "SKIPPED", "target_segment": segment, "reason": "没有通过审核、天气、年龄、日期和容量筛选的合作资源。"})
            continue
        partner = eligible[0]
        components = [_room_component(room)] + _service_components(list(services_data.get("services") or []), segment, party_size) + [_partner_component(partner, party_size)]
        capacity = calculate_capacity({"components": components})
        total_cost = sum((Decimal(str(item["unit_cost"])) * Decimal(str(item["quantity_per_package"])) for item in components), Decimal("0"))
        finance = calculate_finance({
            "total_cost": total_cost,
            "room_min_sell_price": room["min_sell_price"],
            "minimum_margin_rate": "0.25",
            "preferred_price": room["normal_price"],
        })
        finance["minimum_margin_rate"] = 0.25
        clean_partner_name = str(partner["name"]).split("（", 1)[0]
        product = {
            "product_id": f"P{target_date.replace('-', '')}-{index + 1:02d}",
            "status": "READY_FOR_REVIEW",
            "stay_date": target_date,
            "name": f"{room['room_type']}·{clean_partner_name}",
            "tagline": f"{target_date}入住，围绕一项已审核体验安排一晚。",
            "business_goal": "优先消化当前高压力临期房型。",
            "target_segment": segment,
            "purchase_scenario": f"{segment}的杭州一晚轻量周末安排",
            "room_id": room["room_id"],
            "room": dict(room),
            "party_size": party_size,
            "components": components,
            "included_components": [{"id": item["id"], "name": item["name"], "kind": item["kind"], "quantity_per_package": item["quantity_per_package"]} for item in components],
            "capacity": capacity,
            "finance": finance,
            "weather": weather,
            "child_age": 6 if segment == "亲子家庭" else None,
            "constraints": {
                "weather": weather,
                "reservation": "正式合作体验的预约要求以产品确认时的资源记录为准。",
                "cancel_rule": partner.get("cancel_rule"),
            },
            "recommended_route": _route(knowledge_data, segment, rainy=weather in {"小雨", "暴雨"}),
        }
        validation = validate_package({"product": product})["validation"]
        product["validation"] = validation
        if validation["status"] == "PASS":
            product["marketing"] = _marketing(product, partner, room, components)
            if save:
                save_product(product)
        else:
            product["status"] = "PAUSED"
        candidates.append(product)
    pass_count = sum(1 for item in candidates if item.get("validation", {}).get("status") == "PASS")
    return {
        "ok": True,
        "data_notice": "所有本地经营数据均为 competition_test_data；公开 POI 是不可售的带来源路线参考。",
        "opportunity": {
            "inventory": inventory,
            "demand": demand,
            "weather": weather_data,
            "priority_room": {"room_id": priority_room["room_id"], "room_type": priority_room["room_type"]},
        },
        "candidates": candidates,
        "pass_count": pass_count,
        "next_action": "通过候选应由酒店经营者人工确认加入草稿或发布；本地脚本不会自动上架。",
    }


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-09-12")
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    return generate_products(target_date=args.date, count=max(1, min(args.count, 2)), save=args.save)


if __name__ == "__main__":
    run_cli(main)
