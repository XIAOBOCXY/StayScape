import json
from html import escape
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
        variant_index = int(payload.get("variant_index", 0) or 0)
        creative_direction = str(payload.get("creative_direction", "")).strip()
        angles = {
            "FAMILY": ["亲子共创", "亲子研学", "家庭慢游", "亲子发现"],
            "COUPLE": ["双人雅游", "茶香约会", "城市松弛", "宋韵相逢"],
            "LOCAL": ["周末微度假", "城市漫游", "杭州慢生活", "邻里好时光"],
        }
        if creative_direction:
            direction_suffixes = ["首发版", "研学版", "松弛版", "传播版", "轻量版"]
            angle = f"{creative_direction}{direction_suffixes[variant_index % len(direction_suffixes)]}"
        else:
            angle = angles.get(crowd, ["城市体验"])[variant_index % len(angles.get(crowd, ["城市体验"]))]
        name = f"杭州{weather_label}{angle}{partner_name}文化宿"
        if variant_index == 0 and ("非遗" in theme or "非遗" in partner_name):
            name = f"杭州{weather_label}亲子非遗文化宿"
        audience = {"FAMILY": "亲子家庭", "COUPLE": "情侣与朋友", "LOCAL": "本地周末客"}.get(crowd, crowd)
        indoor_hint = "室内文化体验" if payload.get("weather") == "RAIN" else "城市文化体验"
        title = f"{weather_label}的{angle}：住进杭州的文化现场"
        content = (
            f"为{audience}设计的{theme}主题旅居。以{room.get('room_type', '舒适客房')}为基地，"
            f"串联早餐、酒店服务与{partner_name}，在{weather_label}场景下把{indoor_hint}安排进一天的节奏。"
            f"实时房量、体验名额和最低毛利率由系统规则引擎持续校验。"
        )
        poster_title = escape(title, quote=True)
        poster_subtitle = escape(f"{weather_label} · {partner_name}", quote=True)
        poster_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">'
            '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0f766e"/><stop offset="1" stop-color="#d8b56a"/></linearGradient></defs>'
            '<rect width="1080" height="1440" rx="36" fill="url(#bg)"/>'
            '<circle cx="860" cy="240" r="230" fill="#ffffff" opacity=".13"/><circle cx="180" cy="1200" r="310" fill="#ffffff" opacity=".08"/>'
            f'<text x="86" y="190" fill="#fff" font-size="34" font-family="Microsoft YaHei, sans-serif">STAYSCAPE · HANGZHOU</text>'
            f'<text x="86" y="480" fill="#fff" font-size="68" font-weight="700" font-family="Microsoft YaHei, sans-serif">{poster_title}</text>'
            f'<text x="86" y="570" fill="#fff" font-size="34" font-family="Microsoft YaHei, sans-serif">{poster_subtitle}</text>'
            '<rect x="86" y="1050" width="430" height="86" rx="43" fill="#fff" opacity=".92"/>'
            '<text x="136" y="1106" fill="#0f766e" font-size="32" font-weight="700" font-family="Microsoft YaHei, sans-serif">限量临期主题房 · 即刻咨询</text>'
            '</svg>'
        )
        return {
            "product_name": name,
            "theme": theme,
            "target_crowd": crowd,
            "room_inventory_id": int(room.get("id")),
            "hotel_service_ids": service_ids,
            "partner_resource_ids": partner_ids,
            "resource_quantities": quantities,
            "marketing_title": title,
            "marketing_content": content,
            "marketing_assets": [
                {"asset_type": "POSTER", "platform": "酒店大堂 / 小红书封面", "title": title, "content": f"{content} 现在咨询，锁定实时名额。", "visual_brief": "青绿色与宋韵金渐变，留白突出房型、天气和文化体验。", "call_to_action": "扫码咨询 · 名额实时更新", "poster_svg": poster_svg},
                {"asset_type": "SOCIAL_POST", "platform": "小红书 / 朋友圈", "title": f"{weather_label}杭州也值得住一晚", "content": f"{content}｜不追赶行程，把一晚住宿变成一段{partner_name}文化记忆。", "visual_brief": "首图使用文化体验细节，第二张展示早餐与时间安排，末图突出库存紧张提示。", "call_to_action": "评论区咨询可售日期"},
                {"asset_type": "SHORT_VIDEO_SCRIPT", "platform": "短视频 30 秒", "title": f"30秒讲清{angle}套餐", "content": f"0-5秒：天气转变与房间镜头；5-12秒：{room.get('room_type', '客房')}与早餐；12-22秒：{partner_name}体验片段；22-30秒：展示¥{payload.get('preferred_price', '599')}与实时名额，邀请游客提交预约意向。", "visual_brief": "镜头从酒店空间切到杭州文化体验，字幕同步展示真实库存与毛利约束。", "call_to_action": "立即查看可售套餐"},
                {"asset_type": "STORE_CARD", "platform": "OTA / 酒店前台", "title": f"{angle}产品卖点卡", "content": f"{weather_label}友好 · {audience} · {partner_name} · 真实库存动态更新", "visual_brief": "四个图标呈现房间、服务、体验、库存状态。", "call_to_action": "预约意向不收款，先锁定需求"},
            ],
            "recommendation_reason": f"房间、酒店服务和{partner_name}在同一入住日可用，已结合{weather_label}、{audience}和实时容量匹配。",
            "risk_message": "体验名额、房量、天气与价格会实时变化；如有过敏或饮食禁忌，请在预约意向中提前说明并由酒店与商户再次确认。",
        }

    @staticmethod
    def _visitor(payload: dict[str, Any]) -> dict[str, Any]:
        products = payload.get("products", [])
        target_ids = [item["id"] for item in products if item.get("sale_quantity", 0) > 0]
        allergy = payload.get("allergy_information", "")
        natural_language = str(payload.get("natural_language", "")).strip()
        needs_hint = f"已理解你的需求：{natural_language}。" if natural_language else ""
        return {
            "selected_product_ids": target_ids,
            "reasons": {str(item["id"]): f"{needs_hint}预算、天气、同行客群和实时库存均通过规则校验，适合直接提交预约意向。" for item in products if item["id"] in target_ids},
            "schedule_notes": {str(item["id"]): [{"time": "15:00", "title": "办理入住", "description": "酒店前台办理入住并领取体验提示"}, {"time": "16:00", "title": "室内文化体验", "description": "按预约场次参加合作体验"}] for item in products if item["id"] in target_ids},
            "limited_adjustments": {str(item["id"]): ["可在预约意向中备注饮食禁忌与过敏信息", "体验场次以商户实时名额为准"] for item in products if item["id"] in target_ids},
            "allergy_warning": f"已记录过敏信息：{allergy}；酒店与商户需在确认前再次核对。" if allergy else "如有过敏信息，请在预约意向中补充，系统不会替代人工安全确认。",
        }
