import json
from typing import Any


class MockAgent:
    """Deterministic local Agent used for demos, tests, and offline development."""

    def __init__(self, mode: str = "normal") -> None:
        self.mode = mode
        self.calls = 0

    def generate(self, skill_name: str, payload: dict[str, Any]) -> str:
        self.calls += 1
        if self.mode == "timeout":
            raise TimeoutError("mock agent timeout")
        if self.mode in {"invalid", "invalid_once"} and (self.mode == "invalid" or self.calls == 1):
            return "not-json"
        if skill_name == "stayscape-product-generator":
            return json.dumps(self._product(payload), ensure_ascii=False)
        return json.dumps(self._visitor(payload), ensure_ascii=False)

    def repair_json(self, skill_name: str, payload: dict[str, Any], raw_response: str) -> str:
        # The mock repair endpoint demonstrates the same contract as an
        # external Agent repair call while remaining completely deterministic.
        if skill_name == "stayscape-product-generator":
            return json.dumps(self._product(payload), ensure_ascii=False)
        return json.dumps(self._visitor(payload), ensure_ascii=False)

    @staticmethod
    def _product(payload: dict[str, Any]) -> dict[str, Any]:
        room = payload.get("room_inventory") or {}
        selections = payload.get("requested_selections") or []
        service_ids = [item["resource_id"] for item in selections if item["resource_type"] == "HOTEL_SERVICE"]
        partner_ids = [item["resource_id"] for item in selections if item["resource_type"] == "PARTNER_RESOURCE"]
        if not partner_ids:
            partner_ids = [item["id"] for item in payload.get("allowed_partner_resources", [])[:1]]
        quantities = {str(item["resource_id"]): int(item["quantity_per_package"]) for item in selections}
        for item in payload.get("allowed_hotel_services", []):
            if item["id"] in service_ids and str(item["id"]) not in quantities:
                quantities[str(item["id"])] = 1
        for item in payload.get("allowed_partner_resources", []):
            if item["id"] in partner_ids and str(item["id"]) not in quantities:
                quantities[str(item["id"])] = 1
        crowd = payload.get("target_crowd", "FAMILY")
        theme = payload.get("theme", "杭州文化体验")
        weather_label = {"RAIN": "雨天", "SUNNY": "晴日", "CLOUDY": "多云"}.get(payload.get("weather", "RAIN"), "杭州")
        partner_name = next((item["resource_name"] for item in payload.get("allowed_partner_resources", []) if item["id"] in partner_ids), "文化体验")
        name = f"杭州{weather_label}{'亲子' if crowd == 'FAMILY' else ''}{partner_name}文化宿"
        if "非遗" in theme or "非遗" in partner_name:
            name = f"杭州{weather_label}亲子非遗文化宿"
        return {
            "product_name": name,
            "theme": theme,
            "target_crowd": crowd,
            "room_inventory_id": int(room.get("id")),
            "hotel_service_ids": service_ids,
            "partner_resource_ids": partner_ids,
            "resource_quantities": quantities,
            "marketing_title": f"{weather_label}也能把杭州住成一段文化记忆",
            "marketing_content": "一间临期亲子房，串起暖胃早餐、松弛延迟退房与室内文化体验，适合家庭把天气变化变成旅行故事。",
            "recommendation_reason": "房间、酒店服务和室内文化体验在同一入住日可用，时间与客群条件匹配。",
            "risk_message": "体验名额与房量会实时变化；如有过敏或饮食禁忌，请在预约意向中提前说明。",
        }

    @staticmethod
    def _visitor(payload: dict[str, Any]) -> dict[str, Any]:
        products = payload.get("products", [])
        target_ids = [item["id"] for item in products if item.get("sale_quantity", 0) > 0]
        allergy = payload.get("allergy_information", "")
        return {
            "selected_product_ids": target_ids,
            "reasons": {str(item["id"]): "预算、天气与同行客群均满足，且当前仍有可售库存。" for item in products if item["id"] in target_ids},
            "schedule_notes": {str(item["id"]): [{"time": "15:00", "title": "办理入住", "description": "酒店前台办理入住并领取体验提示"}, {"time": "16:00", "title": "室内文化体验", "description": "按预约场次参加合作体验"}] for item in products if item["id"] in target_ids},
            "limited_adjustments": {str(item["id"]): ["可在预约意向中备注饮食禁忌与过敏信息", "体验场次以商户实时名额为准"] for item in products if item["id"] in target_ids},
            "allergy_warning": f"已记录过敏信息：{allergy}；酒店与商户需在确认前再次核对。" if allergy else "如有过敏信息，请在预约意向中补充，系统不会替代人工安全确认。",
        }

