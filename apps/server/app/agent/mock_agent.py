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
        requested_partner_ids = [item["resource_id"] for item in selections if item["resource_type"] == "PARTNER_RESOURCE"]
        variant_index = int(payload.get("variant_index", 0) or 0)
        # Multiple partner selections represent alternative packages, not one
        # package that consumes every activity. Pick one deterministic option
        # per variant so candidates can have different schedules safely.
        partner_ids = [requested_partner_ids[variant_index % len(requested_partner_ids)]] if requested_partner_ids else []
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
        partner = next((item for item in payload.get("allowed_partner_resources", []) if item["id"] in partner_ids), {})
        service_names = "、".join(item.get("service_name", "酒店服务") for item in payload.get("allowed_hotel_services", []) if item["id"] in service_ids) or "酒店服务"
        partner_time = "-".join(item for item in (partner.get("start_time"), partner.get("end_time")) if item) or "场次待确认"
        partner_address = partner.get("address") or "杭州文化体验场地"
        partner_description = partner.get("description") or f"{partner_name}，把杭州文化放进一晚旅居。"
        partner_capacity = partner.get("remaining_capacity") or 0
        indoor_hint = "室内文化体验" if payload.get("weather") == "RAIN" else "城市文化体验"
        title = f"{weather_label}的{angle}：住进杭州的文化现场"
        content = (
            f"为{audience}设计的{theme}主题旅居。以{room.get('room_type', '舒适客房')}为基地，"
            f"把{service_names}和{partner_name}排进同一张时间卡：{partner_time}，地点在{partner_address}。"
            f"{partner_description}在{weather_label}场景下，{indoor_hint}不再是空泛口号，而是可直接预约的真实场次。"
            f"当前合作体验余{partner_capacity}个名额，房量、体验名额和最低毛利率由规则引擎持续校验。"
        )
        safe = lambda value: escape(str(value), quote=True)
        poster_title = safe(title[:24])
        poster_subtitle = safe(f"{weather_label} · {partner_name} · {payload.get('target_date', '')}")
        poster_location = safe(partner_address[:22])
        poster_time = safe(partner_time)
        poster_room = safe(room.get("room_type", "舒适客房"))
        poster_partner = safe(partner_name[:18])
        poster_price = safe(payload.get("preferred_price", "599"))
        scene_text = f"{theme} {partner_name} {partner_description} {crowd}".lower()
        if any(word in scene_text for word in ("非遗", "手作", "工坊", "craft")):
            scene_art = '<g><rect x="130" y="535" width="430" height="55" rx="12" fill="#d19b5d"/><rect x="180" y="455" width="320" height="86" rx="14" fill="#f6e8ce"/><circle cx="250" cy="496" r="28" fill="#e9a56e"/><circle cx="410" cy="496" r="28" fill="#7db5a8"/><path d="M305 465 l55 60 M360 465 l-55 60" stroke="#174d46" stroke-width="10" stroke-linecap="round"/><path d="M190 415 q120 -74 240 0" fill="none" stroke="#f7d48e" stroke-width="18"/><circle cx="190" cy="415" r="12" fill="#d45c53"/><circle cx="430" cy="415" r="12" fill="#d45c53"/><text x="150" y="630" fill="#174d46" font-size="27" font-weight="700" font-family="Microsoft YaHei, sans-serif">亲子一起做一件杭州手作</text></g>'
        elif any(word in scene_text for word in ("茶", "点茶", "tea")):
            scene_art = '<g><ellipse cx="420" cy="570" rx="270" ry="52" fill="#c38f55"/><path d="M275 520 q0 -90 100 -90 q100 0 100 90 v32 H275Z" fill="#f5e5c6" stroke="#174d46" stroke-width="8"/><path d="M475 475 q85 -12 85 48 q0 58 -85 36" fill="none" stroke="#174d46" stroke-width="12"/><path d="M370 430 q-12 -70 28 -95 M430 430 q20 -72 -8 -106" fill="none" stroke="#fff8e7" stroke-width="9" stroke-linecap="round"/><circle cx="220" cy="525" r="28" fill="#78a66f"/><path d="M200 540 q45 -75 80 -8" fill="none" stroke="#174d46" stroke-width="8"/><text x="170" y="630" fill="#174d46" font-size="27" font-weight="700" font-family="Microsoft YaHei, sans-serif">一席茶，慢下来认识杭州</text></g>'
        elif any(word in scene_text for word in ("情侣", "旅拍", "运河", "西湖", "couple")):
            scene_art = '<g><path d="M80 520 Q260 420 470 520 T1010 500 V658 H80Z" fill="#2c716b" opacity=".85"/><path d="M70 568 Q300 510 560 580 T1010 555" fill="none" stroke="#f8e1aa" stroke-width="12"/><path d="M180 540 Q420 360 660 540" fill="none" stroke="#174d46" stroke-width="18"/><circle cx="290" cy="450" r="17" fill="#f2bc87"/><circle cx="372" cy="450" r="17" fill="#f2bc87"/><path d="M290 468 l-18 72 M372 468 l18 72 M275 490 l95 0" stroke="#d45c53" stroke-width="16" stroke-linecap="round"/><path d="M770 280 v300 M850 320 v260" stroke="#174d46" stroke-width="14"/><path d="M730 290 q40 -58 80 0 q-40 58 -80 0 M810 330 q40 -58 80 0 q-40 58 -80 0" fill="#f2c777"/><text x="170" y="630" fill="#174d46" font-size="27" font-weight="700" font-family="Microsoft YaHei, sans-serif">把湖光与夜色留在相册里</text></g>'
        else:
            scene_art = '<g><rect x="690" y="285" width="250" height="230" rx="15" fill="#f8efe0" opacity=".96"/><rect x="725" y="325" width="75" height="100" rx="5" fill="#87bbb0"/><rect x="835" y="325" width="75" height="100" rx="5" fill="#87bbb0"/><path d="M675 285 L815 205 L955 285Z" fill="#174d46"/><rect x="785" y="425" width="68" height="90" fill="#d6ad68"/><circle cx="820" cy="470" r="5" fill="#174d46"/><path d="M180 525 q0 -80 60 -80 t60 80" fill="#d45c53"/><circle cx="240" cy="430" r="25" fill="#f0bd87"/><path d="M185 535 q55 -30 110 0" fill="none" stroke="#174d46" stroke-width="11"/><text x="120" y="630" fill="#174d46" font-size="27" font-weight="700" font-family="Microsoft YaHei, sans-serif">住进一晚，把杭州玩得更具体</text></g>'
        poster_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">'
            '<defs><linearGradient id="paper" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#f9f4e8"/><stop offset="1" stop-color="#e8f4ee"/></linearGradient><linearGradient id="scene" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#8fc9c0"/><stop offset="1" stop-color="#e8c77a"/></linearGradient><filter id="shadow"><feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#174d46" flood-opacity=".18"/></filter></defs>'
            '<rect width="1080" height="1440" rx="36" fill="url(#paper)"/>'
            '<circle cx="960" cy="80" r="180" fill="#d8b56a" opacity=".18"/><circle cx="40" cy="1360" r="230" fill="#0f766e" opacity=".08"/>'
            '<text x="72" y="90" fill="#0f766e" font-size="26" font-weight="700" letter-spacing="4" font-family="Arial, Microsoft YaHei, sans-serif">STAYSCAPE · HANGZHOU</text>'
            '<rect x="60" y="128" width="960" height="530" rx="34" fill="url(#scene)" filter="url(#shadow)"/>'
            '<path d="M60 470 Q220 350 370 460 T680 440 T1020 420 V658 H60Z" fill="#3f8c7e" opacity=".78"/><path d="M60 540 Q260 475 470 550 T1020 520 V658 H60Z" fill="#2c716b" opacity=".65"/><path d="M60 585 Q280 540 520 600 T1020 580 V658 H60Z" fill="#f4dfad" opacity=".82"/>'
            '<path d="M78 604 Q280 555 470 610 T1000 594" fill="none" stroke="#fff8e7" stroke-width="7" opacity=".75"/>'
            '<rect x="710" y="285" width="220" height="210" rx="12" fill="#f8efe0" opacity=".96"/><rect x="746" y="322" width="62" height="88" rx="5" fill="#87bbb0"/><rect x="833" y="322" width="62" height="88" rx="5" fill="#87bbb0"/><path d="M700 285 L820 215 L940 285Z" fill="#174d46"/><rect x="780" y="425" width="72" height="70" fill="#d6ad68"/><circle cx="816" cy="460" r="5" fill="#174d46"/>'
            '<path d="M205 508 Q200 455 252 438 Q304 455 299 508Z" fill="#e7a75c"/><path d="M252 438 L252 500" stroke="#174d46" stroke-width="8"/><circle cx="252" cy="430" r="24" fill="#f0bd87"/><path d="M214 520 Q252 492 290 520" fill="none" stroke="#174d46" stroke-width="10"/><path d="M170 408 Q252 340 334 408" fill="#d45c53"/><path d="M170 408 Q252 450 334 408" fill="none" stroke="#8d3f3c" stroke-width="5"/>'
            '<rect x="118" y="548" width="270" height="62" rx="31" fill="#fff" opacity=".92"/><text x="150" y="588" fill="#174d46" font-size="25" font-weight="700" font-family="Microsoft YaHei, sans-serif">杭州文化现场</text>'
            '<g opacity=".76"><path d="M930 164 l-14 38 M968 170 l-14 38 M1006 176 l-14 38" stroke="#fff" stroke-width="8" stroke-linecap="round"/><circle cx="930" cy="145" r="10" fill="#fff"/><circle cx="968" cy="151" r="10" fill="#fff"/><circle cx="1006" cy="157" r="10" fill="#fff"/></g>'
            f'<text x="72" y="736" fill="#174d46" font-size="55" font-weight="700" font-family="Microsoft YaHei, sans-serif">{poster_title}</text>'
            f'<text x="74" y="788" fill="#5b756e" font-size="25" font-family="Microsoft YaHei, sans-serif">{poster_subtitle}</text>'
            f'<rect x="70" y="838" width="940" height="180" rx="22" fill="#fff" stroke="#d8e7df"/><circle cx="126" cy="900" r="30" fill="#e7f3ed"/><path d="M110 900 h32 M126 884 v32" stroke="#0f766e" stroke-width="6"/><text x="180" y="895" fill="#174d46" font-size="27" font-weight="700" font-family="Microsoft YaHei, sans-serif">住进一晚，把杭州玩得更具体</text><text x="180" y="940" fill="#6b827b" font-size="22" font-family="Microsoft YaHei, sans-serif">{poster_room}  ·  {poster_partner}</text><text x="180" y="978" fill="#6b827b" font-size="20" font-family="Microsoft YaHei, sans-serif">{poster_time}  ·  {poster_location}</text>'
            '<rect x="70" y="1050" width="450" height="190" rx="22" fill="#174d46"/><text x="104" y="1100" fill="#bfe5d7" font-size="20" font-family="Microsoft YaHei, sans-serif">真实库存驱动的主题住宿</text><text x="104" y="1170" fill="#fff" font-size="54" font-weight="700" font-family="Arial, Microsoft YaHei, sans-serif">¥' + poster_price + '</text><text x="104" y="1210" fill="#d7efe6" font-size="20" font-family="Microsoft YaHei, sans-serif">/ 套 · 名额实时更新</text>'
            '<rect x="550" y="1050" width="460" height="190" rx="22" fill="#f2dfac"/><text x="586" y="1100" fill="#7b5b2a" font-size="20" font-family="Microsoft YaHei, sans-serif">今日行动建议</text><text x="586" y="1152" fill="#174d46" font-size="28" font-weight="700" font-family="Microsoft YaHei, sans-serif">先看场次，再锁意向</text><text x="586" y="1198" fill="#6b6250" font-size="20" font-family="Microsoft YaHei, sans-serif">不收款 · 酒店与商户二次确认</text>'
            '<text x="72" y="1330" fill="#5b756e" font-size="21" font-family="Microsoft YaHei, sans-serif">#杭州亲子游  #临期主题房  #住进文化现场</text>'
            '</svg>'
        )
        # Keep the existing poster layout/data contract, but replace the old
        # generic mountain scene with an illustration tied to the selected
        # culture, tea, city or family theme.
        scene_start = poster_svg.find('<path d="M60 470')
        scene_end = poster_svg.find('</g>', scene_start)
        if scene_start >= 0 and scene_end >= 0:
            poster_svg = poster_svg[:scene_start] + scene_art + poster_svg[scene_end + 4:]
        social_post = (
            f"{weather_label}的杭州，也值得住一晚 🌿\n\n"
            f"不是把房间打折，而是把{room.get('room_type', '舒适客房')}、{service_names}和{partner_name}排成一段刚刚好的旅程。\n"
            f"📍 {partner_address}\n🕓 {partner_time}\n🧒 适合：{audience}\n💰 参考价：¥{payload.get('preferred_price', '599')} / 套\n\n"
            f"{partner_description}\n\n"
            "下雨就去室内做手作，晴天就把杭州的风景留在相册里。名额和房量实时变化，先收藏，再来问我今天还能不能订到。\n\n"
            "#杭州亲子游 #杭州住宿 #非遗体验 #周末微度假 #旅行灵感"
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
                {"asset_type": "POSTER", "platform": "酒店大堂 / 小红书封面", "title": title, "content": f"{content}\n\n现在咨询，锁定实时名额。", "visual_brief": "四段式场景海报：杭州山水与酒店窗景、体验人物/手作桌面、真实场次与地址、价格和库存行动卡；不是纯背景文字。", "call_to_action": "扫码咨询 · 名额实时更新", "poster_svg": poster_svg},
                {"asset_type": "SOCIAL_POST", "platform": "小红书 / 朋友圈", "title": f"{weather_label}杭州也值得住一晚", "content": social_post, "visual_brief": "建议做 4:5 首图 + 体验细节图 + 时间卡 + 预约提示图，首图突出具体场景，正文用短句、emoji 和可执行信息。", "call_to_action": "评论区咨询可售日期"},
                {"asset_type": "SHORT_VIDEO_SCRIPT", "platform": "短视频 30 秒", "title": f"30秒讲清{angle}套餐", "content": f"0-3秒：{weather_label}与杭州窗景建立情绪；3-8秒：推入{room.get('room_type', '客房')}，拍到{room.get('features', '房间细节')}；8-15秒：早餐/服务细节和{service_names}；15-23秒：{partner_name}的{partner_description}，打出{partner_time}与{partner_address}；23-27秒：展示¥{payload.get('preferred_price', '599')}、余{partner_capacity}个体验名额；27-30秒：字幕“先看场次，再提交预约意向”。", "visual_brief": "镜头必须拍到房间、服务、文化体验和地址时间四类具体画面，字幕只做信息强化。", "call_to_action": "立即查看可售套餐"},
                {"asset_type": "STORE_CARD", "platform": "OTA / 酒店前台", "title": f"{angle}产品卖点卡", "content": f"{weather_label}友好｜{room.get('room_type', '舒适客房')}｜{service_names}｜{partner_name}\n场次 {partner_time} · {partner_address}\n适合 {audience} · 参考价 ¥{payload.get('preferred_price', '599')} · 体验余{partner_capacity}个名额", "visual_brief": "用房间、早餐、手作、地图四个信息模块代替大段宣传语，价格和场次放在首屏。", "call_to_action": "预约意向不收款，先锁定需求"},
            ],
            "recommendation_reason": f"{room.get('room_type', '客房')}、{service_names}和{partner_name}在{payload.get('target_date', '入住当日')}可用，场次为{partner_time}，地点为{partner_address}；系统已结合{weather_label}、{audience}、真实容量和毛利约束匹配。",
            "risk_message": "体验名额、房量、天气与价格会实时变化；如有过敏或饮食禁忌，请在预约意向中提前说明并由酒店与商户再次确认。",
        }

    @staticmethod
    def _visitor(payload: dict[str, Any]) -> dict[str, Any]:
        products = payload.get("products", [])
        target_ids = [item["id"] for item in products if item.get("sale_quantity", 0) > 0]
        allergy = payload.get("allergy_information", "")
        natural_language = str(payload.get("natural_language", "")).strip()
        needs_hint = f"已理解你的需求：{natural_language}。" if natural_language else ""
        question = str(payload.get("question", "")).strip()
        if question:
            answer = f"{needs_hint}关于“{question}”，我会优先依据当前产品的真实场次、库存、天气和适龄范围回答；最终预约以前台与商户确认结果为准。"
        elif target_ids:
            answer = f"{needs_hint}当前有{len(target_ids)}个套餐通过了预算、人数、天气和库存校验，可以继续查看时间安排并提交预约意向。"
        else:
            answer = f"{needs_hint}暂时没有同时满足这些条件的可售套餐；可以放宽日期、预算或体验偏好，我会继续帮你匹配。"
        return {
            "answer": answer,
            "safety_notes": "过敏、儿童安全和体验场次需要酒店与商户在确认前再次人工核对。",
            "selected_product_ids": target_ids,
            "reasons": {str(item["id"]): f"{needs_hint}预算、天气、同行客群和实时库存均通过规则校验，适合直接提交预约意向。" for item in products if item["id"] in target_ids},
            "schedule_notes": {str(item["id"]): [{"time": "15:00", "title": "办理入住", "description": "酒店前台办理入住并领取体验提示"}, {"time": "16:00", "title": "室内文化体验", "description": "按预约场次参加合作体验"}] for item in products if item["id"] in target_ids},
            "limited_adjustments": {str(item["id"]): ["可在预约意向中备注饮食禁忌与过敏信息", "体验场次以商户实时名额为准"] for item in products if item["id"] in target_ids},
            "allergy_warning": f"已记录过敏信息：{allergy}；酒店与商户需在确认前再次核对。" if allergy else "如有过敏信息，请在预约意向中补充，系统不会替代人工安全确认。",
        }
