"""Deterministic offline Agent used by the demo and automated tests.

The mock creates creative candidates from the supplied resource metadata.  It
never owns inventory, pricing, margin or publication decisions; those remain
inside ProductService and the rules package.
"""

from __future__ import annotations

import json
from html import escape
from typing import Any


class MockAgent:
    """Local Agent contract with deterministic, theme-aware output."""

    PROFILE_RULES = {
        "THEME_PARK": {"key": "themepark", "label": "主题乐园", "suffix": "欢乐宿", "tag": "THEME PARK", "hashtags": "#杭州乐园 #亲子周末 #城市游乐"},
        "KIDS": {"key": "kids", "label": "儿童探索", "suffix": "儿童探索宿", "tag": "KIDS", "hashtags": "#杭州亲子游 #雨天去哪儿 #儿童乐园"},
        "NATURE": {"key": "nature", "label": "自然探索", "suffix": "自然探索宿", "tag": "NATURE", "hashtags": "#西溪湿地 #自然课堂 #杭州亲子游"},
        "SPORT": {"key": "sport", "label": "运动娱乐", "suffix": "运动挑战宿", "tag": "SPORT", "hashtags": "#杭州运动 #朋友周末 #想刺激一点"},
        "NIGHTLIFE": {"key": "nightlife", "label": "杭州夜游", "suffix": "夜游宿", "tag": "NIGHTLIFE", "hashtags": "#杭州夜游 #运河夜景 #城市夜生活"},
        "PHOTO": {"key": "photo", "label": "城市旅拍", "suffix": "旅拍宿", "tag": "PHOTO", "hashtags": "#杭州旅拍 #西湖夜景 #旅行记录"},
        "FOOD": {"key": "food", "label": "江南味觉", "suffix": "美食宿", "tag": "FOOD", "hashtags": "#杭帮菜 #杭州美食 #旅行吃什么"},
        "PERFORMANCE": {"key": "performance", "label": "城市演出", "suffix": "演出宿", "tag": "PERFORMANCE", "hashtags": "#杭州演出 #夜间文化 #城市周末"},
        "ENTERTAINMENT": {"key": "entertainment", "label": "城市娱乐", "suffix": "娱乐宿", "tag": "ENTERTAINMENT", "hashtags": "#杭州娱乐 #朋友出行 #夜间生活"},
        "CITY_WALK": {"key": "city_walk", "label": "城市漫游", "suffix": "漫游宿", "tag": "CITY WALK", "hashtags": "#杭州漫游 #城市散步 #一个人的旅行"},
        "CULTURE": {"key": "culture", "label": "杭州手作", "suffix": "文化宿", "tag": "CULTURE", "hashtags": "#杭州非遗 #亲子手作 #旅行灵感"},
        "TEA": {"key": "tea", "label": "茶香慢生活", "suffix": "茶旅宿", "tag": "TEA", "hashtags": "#杭州茶文化 #慢旅行 #茶空间"},
    }
    CROWD_LABELS = {
        "FAMILY": "亲子家庭",
        "COUPLE": "情侣与朋友",
        "FRIENDS": "朋友小组",
        "SOLO": "独自出发的旅行者",
        "LOCAL_WEEKEND": "杭州本地周末客",
    }

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
        if skill_name == "stayscape-product-generator":
            return json.dumps(self._product(payload), ensure_ascii=False)
        return json.dumps(self._visitor(payload), ensure_ascii=False)

    @classmethod
    def _profile(cls, payload: dict[str, Any], partner: dict[str, Any]) -> dict[str, str]:
        category = str(partner.get("category", "")).upper()
        text = f"{payload.get('theme', '')} {partner.get('resource_name', '')} {partner.get('description', '')}".lower()
        aliases = (
            ("THEME_PARK", ("乐园", "主题公园", "themepark", "theme park")),
            ("KIDS", ("儿童乐园", "儿童探索", "kids")),
            ("SPORT", ("攀岩", "卡丁车", "射箭", "运动", "sport")),
            ("NIGHTLIFE", ("夜游", "夜景", "运河夜", "nightlife")),
            ("PHOTO", ("旅拍", "摄影", "照片", "photo")),
            ("FOOD", ("美食", "杭帮菜", "甜品", "咖啡", "烘焙", "food")),
            ("NATURE", ("自然", "湿地", "动物", "植物", "nature")),
            ("PERFORMANCE", ("演出", "剧场", "音乐现场", "performance")),
            ("ENTERTAINMENT", ("娱乐", "陶艺", "桌游", "密室", "vr")),
            ("CITY_WALK", ("漫游", "路线", "街巷", "city walk")),
            ("TEA", ("茶", "点茶", "tea")),
            ("CULTURE", ("非遗", "手作", "丝绸", "香囊", "文化", "craft")),
        )
        for key, words in aliases:
            if category == key or any(word in text for word in words):
                return cls.PROFILE_RULES[key]
        crowd = str(payload.get("target_crowd", "")).upper()
        return cls.PROFILE_RULES["KIDS" if crowd == "FAMILY" else "CITY_WALK"]

    @classmethod
    def _pick_partner(cls, payload: dict[str, Any], requested_ids: list[int], variant_index: int) -> dict[str, Any]:
        allowed = list(payload.get("allowed_partner_resources", []))
        pool = [item for item in allowed if item.get("id") in requested_ids] if requested_ids else allowed
        if not pool:
            return {}
        if requested_ids:
            return pool[variant_index % len(pool)]
        theme = str(payload.get("theme", "")).lower()
        crowd = str(payload.get("target_crowd", "")).upper()
        weather = str(payload.get("weather", "")).upper()

        def affinity(item: dict[str, Any]) -> tuple[int, int, int]:
            profile = cls._profile(payload, item)
            text = f"{profile['key']} {item.get('resource_name', '')} {item.get('description', '')}".lower()
            score = sum(5 for word in (theme, crowd.lower(), weather.lower()) if word and word in text)
            if weather == "RAIN" and item.get("indoor"):
                score += 3
            if weather != "RAIN" and not item.get("indoor"):
                score += 2
            return (-score, int(item.get("settlement_price", 0) or 0), int(item.get("id", 0)))

        return sorted(pool, key=affinity)[variant_index % len(pool)]

    @classmethod
    def _poster_svg(cls, *, profile: dict[str, str], title: str, partner_name: str, room_name: str, weather_label: str, price: str, partner_address: str) -> str:
        palette = {
            "themepark": ("#e9a34d", "#1c5e54", "#fff0cc"),
            "kids": ("#e17b64", "#24695e", "#fff1d4"),
            "nature": ("#6a9b70", "#245a50", "#e9f3df"),
            "sport": ("#4e7d9e", "#1c5360", "#e5f3f5"),
            "nightlife": ("#6e5b9b", "#202b4d", "#f1e7ff"),
            "photo": ("#d49a79", "#284e56", "#ffe9d8"),
            "food": ("#c87b4a", "#5a3f2f", "#fff0dc"),
            "performance": ("#9d5f78", "#4d2744", "#fce5ee"),
            "entertainment": ("#6b8eb8", "#243b5b", "#e8f2ff"),
            "city_walk": ("#7fa9a2", "#21554f", "#e8f3ed"),
            "culture": ("#d19b5d", "#174d46", "#f6e8ce"),
            "tea": ("#86a66d", "#365a48", "#eff3dc"),
        }
        accent, dark, light = palette.get(profile["key"], ("#d19b5d", "#174d46", "#f6e8ce"))
        safe = lambda value: escape(str(value), quote=True)
        art = {
            "themepark": '<circle cx="270" cy="410" r="88" fill="#fff" opacity=".7"/><path d="M205 410 Q270 315 335 410" fill="none" stroke="#fff" stroke-width="12"/><path d="M225 415 v88 M315 415 v88" stroke="#fff" stroke-width="10"/><circle cx="270" cy="365" r="18" fill="#fff"/>',
            "kids": '<rect x="155" y="370" width="240" height="130" rx="22" fill="#fff" opacity=".8"/><circle cx="215" cy="430" r="30" fill="#e9a56e"/><circle cx="335" cy="430" r="30" fill="#7db5a8"/><path d="M240 455 Q275 490 310 455" fill="none" stroke="#24695e" stroke-width="10"/>',
            "nature": '<path d="M120 510 Q235 300 350 510" fill="#fff" opacity=".75"/><path d="M235 515 V350 M235 410 Q170 365 135 410 M235 430 Q300 380 345 420" fill="none" stroke="#245a50" stroke-width="12"/><circle cx="690" cy="350" r="48" fill="#fff" opacity=".7"/>',
            "sport": '<path d="M160 500 L220 330 L300 500" fill="none" stroke="#fff" stroke-width="24" stroke-linecap="round"/><circle cx="225" cy="320" r="28" fill="#f6c06e"/><path d="M430 460 q115 -80 230 0" fill="none" stroke="#fff" stroke-width="20"/>',
            "nightlife": '<circle cx="250" cy="390" r="82" fill="#f4d488" opacity=".9"/><path d="M180 520 Q300 380 430 520" fill="none" stroke="#fff" stroke-width="16"/><path d="M685 260 v270 M745 300 v230 M805 250 v280" stroke="#fff" stroke-width="10"/><circle cx="685" cy="245" r="12" fill="#f4d488"/><circle cx="745" cy="285" r="12" fill="#f4d488"/>',
            "photo": '<rect x="150" y="350" width="270" height="170" rx="20" fill="#fff" opacity=".8"/><circle cx="285" cy="435" r="54" fill="#d49a79"/><circle cx="285" cy="435" r="30" fill="#284e56"/><path d="M480 500 Q625 340 790 500" fill="none" stroke="#fff" stroke-width="14"/>',
            "food": '<ellipse cx="270" cy="500" rx="180" ry="34" fill="#fff" opacity=".8"/><path d="M140 470 Q160 330 270 330 Q380 330 400 470Z" fill="#fff" opacity=".75"/><circle cx="220" cy="405" r="23" fill="#c87b4a"/><circle cx="300" cy="390" r="23" fill="#e5bb69"/>',
            "performance": '<path d="M150 500 Q300 330 450 500" fill="#fff" opacity=".75"/><circle cx="245" cy="410" r="24" fill="#9d5f78"/><circle cx="355" cy="410" r="24" fill="#4d2744"/><path d="M230 450 Q300 500 370 450" fill="none" stroke="#4d2744" stroke-width="14"/>',
            "entertainment": '<rect x="145" y="360" width="280" height="170" rx="24" fill="#fff" opacity=".78"/><circle cx="215" cy="445" r="28" fill="#6b8eb8"/><circle cx="355" cy="445" r="28" fill="#243b5b"/><path d="M245 445 h80" stroke="#243b5b" stroke-width="12"/>',
            "city_walk": '<path d="M90 520 Q260 390 430 520 T790 510" fill="none" stroke="#fff" stroke-width="22"/><path d="M550 500 v-190 M650 500 v-230" stroke="#21554f" stroke-width="18"/><circle cx="550" cy="285" r="23" fill="#f4d488"/>',
            "culture": '<rect x="145" y="420" width="300" height="70" rx="12" fill="#d19b5d"/><path d="M210 390 l80 120 M370 390 l-80 120" stroke="#174d46" stroke-width="13" stroke-linecap="round"/><circle cx="210" cy="370" r="16" fill="#d45c53"/><circle cx="370" cy="370" r="16" fill="#d45c53"/>',
            "tea": '<ellipse cx="285" cy="480" rx="180" ry="36" fill="#fff" opacity=".7"/><path d="M175 440 Q175 330 285 330 Q395 330 395 440Z" fill="#fff" opacity=".85"/><path d="M395 370 Q480 360 460 435 Q445 480 395 450" fill="none" stroke="#365a48" stroke-width="14"/>',
        }.get(profile["key"], "")
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">'
            f'<rect width="1080" height="1440" rx="36" fill="{light}"/><circle cx="900" cy="140" r="230" fill="{accent}" opacity=".25"/>'
            f'<text x="72" y="90" fill="{dark}" font-size="26" font-weight="700" letter-spacing="4" font-family="Arial, Microsoft YaHei, sans-serif">STAYSCAPE · HANGZHOU</text>'
            f'<rect x="60" y="128" width="960" height="560" rx="34" fill="{accent}"/><path d="M60 560 Q240 450 430 560 T760 540 T1020 500 V688 H60Z" fill="{dark}" opacity=".42"/>'
            f'<g>{art}</g><text x="100" y="770" fill="{dark}" font-size="56" font-weight="700" font-family="Microsoft YaHei, sans-serif">{safe(title[:22])}</text>'
            f'<text x="104" y="820" fill="{dark}" font-size="24" font-family="Microsoft YaHei, sans-serif">{safe(weather_label)} · {safe(profile["tag"])} · {safe(partner_name[:20])}</text>'
            f'<rect x="70" y="885" width="940" height="190" rx="24" fill="#fff" opacity=".85"/><text x="110" y="945" fill="{dark}" font-size="25" font-weight="700" font-family="Microsoft YaHei, sans-serif">住进 {safe(room_name)}，把 {safe(profile["label"])} 放进今晚</text>'
            f'<text x="110" y="995" fill="#5b756e" font-size="22" font-family="Microsoft YaHei, sans-serif">{safe(partner_address[:28])}</text><text x="110" y="1035" fill="#5b756e" font-size="22" font-family="Microsoft YaHei, sans-serif">真实场次 · 实时余量 · 到店后按时间卡体验</text>'
            f'<rect x="70" y="1110" width="420" height="190" rx="24" fill="{dark}"/><text x="105" y="1170" fill="#c9eadc" font-size="20" font-family="Microsoft YaHei, sans-serif">从临期库存重新设计的杭州体验</text><text x="105" y="1250" fill="#fff" font-size="56" font-weight="700" font-family="Arial, sans-serif">¥{safe(price)}</text>'
            f'<rect x="530" y="1110" width="480" height="190" rx="24" fill="#f2dfad"/><text x="570" y="1170" fill="#7b5b2a" font-size="23" font-weight="700" font-family="Microsoft YaHei, sans-serif">{safe(profile["label"])} · {safe(partner_name[:14])}</text><text x="570" y="1220" fill="#6b6250" font-size="21" font-family="Microsoft YaHei, sans-serif">打开 StayScape，查看可售名额</text>'
            f'<text x="72" y="1370" fill="#5b756e" font-size="21" font-family="Microsoft YaHei, sans-serif">#杭州旅行 #StayScape #{safe(profile["key"])}</text></svg>'
        )

    @classmethod
    def _product(cls, payload: dict[str, Any]) -> dict[str, Any]:
        room = payload.get("room_inventory") or {}
        selections = payload.get("requested_selections") or []
        service_ids = [item["resource_id"] for item in selections if item["resource_type"] == "HOTEL_SERVICE"]
        requested_partner_ids = [item["resource_id"] for item in selections if item["resource_type"] == "PARTNER_RESOURCE"]
        variant_index = int(payload.get("variant_index", 0) or 0)
        partner = cls._pick_partner(payload, requested_partner_ids, variant_index)
        partner_ids = [partner["id"]] if partner else []
        quantities = {str(item["resource_id"]): int(item["quantity_per_package"]) for item in selections}
        for item in payload.get("allowed_hotel_services", []):
            if item["id"] in service_ids and str(item["id"]) not in quantities:
                quantities[str(item["id"])] = 1
        if partner and str(partner["id"]) not in quantities:
            quantities[str(partner["id"])] = 1

        crowd = str(payload.get("target_crowd", "FAMILY")).upper()
        theme = str(payload.get("theme", "杭州城市体验"))
        weather = str(payload.get("weather", "RAIN")).upper()
        weather_label = {"RAIN": "雨天", "SUNNY": "晴日", "CLOUDY": "多云"}.get(weather, "杭州")
        profile = cls._profile(payload, partner)
        partner_name = partner.get("resource_name", profile["label"])
        room_name = room.get("room_type", "舒适客房")
        audience = cls.CROWD_LABELS.get(crowd, crowd)
        service_names = "、".join(item.get("service_name", "酒店服务") for item in payload.get("allowed_hotel_services", []) if item["id"] in service_ids) or "酒店服务"
        partner_time = "-".join(item for item in (partner.get("start_time"), partner.get("end_time")) if item) or "场次待确认"
        partner_address = partner.get("address") or "杭州体验场地"
        partner_description = partner.get("description") or f"{partner_name}，让杭州的这一晚有具体去处。"
        capacity = partner.get("remaining_capacity") or 0
        suffix = ["", "·探索版", "·轻享版", "·深玩版", "·周末版"][variant_index % 5]
        if variant_index == 0 and crowd == "FAMILY" and ("非遗" in theme or "非遗" in partner_name):
            name = "杭州雨天亲子非遗文化宿"
        else:
            name = f"杭州{weather_label}{profile['label']}{profile['suffix']} · {partner_name[:8]}{suffix}"
        title = f"{weather_label}的{name.replace('杭州', '', 1)}：把{profile['label']}放进一晚旅居"
        content = (
            f"为{audience}设计的{theme}主题旅居。以{room_name}为基地，"
            f"把{service_names}与{partner_name}排进同一张时间卡：{partner_time}，地点在{partner_address}。"
            f"{partner_description}在{weather_label}场景下，这不是一句泛泛的宣传语，而是可按真实场次体验的城市内容。"
            f"当前合作体验余{capacity}个名额，房量、体验名额、成本、售价与毛利率由规则引擎持续校验。"
        )
        poster_svg = cls._poster_svg(profile=profile, title=title, partner_name=partner_name, room_name=room_name, weather_label=weather_label, price=payload.get("preferred_price", "599"), partner_address=partner_address)
        social_post = (
            f"{weather_label}的杭州，也值得住一晚。\n\n"
            f"{partner_description}\n\n"
            f"这次把 {room_name}、{service_names} 和 {partner_name} 排成一张轻松的时间卡。\n"
            f"不用赶很多景点，按 {partner_time} 去 {partner_address}，把{profile['label']}变成旅程里最具体的一段。\n\n"
            f"预算参考 ¥{payload.get('preferred_price', '599')} / 套 · 当前余 {capacity} 个名额\n\n"
            f"{profile['hashtags']} #杭州酒店 #StayScape"
        )
        short_video = (
            f"0-3秒：{weather_label}城市/酒店窗景；3-8秒：{room_name}与{service_names}；"
            f"8-18秒：拍到{partner_name}的真实体验画面；18-25秒：字幕显示{partner_time}与{partner_address}；"
            f"25-30秒：展示¥{payload.get('preferred_price', '599')}、余{capacity}个名额，提示先查看场次再提交预约意向。"
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
                {"asset_type": "POSTER", "platform": "StayScape / 小红书封面", "title": title, "content": content, "visual_brief": f"以{profile['label']}（{profile['tag']}）为主视觉，画面包含{partner_name}、{room_name}与真实场次信息，不使用空泛纯色背景。", "call_to_action": "查看场次 · 提交预约意向", "poster_svg": poster_svg},
                {"asset_type": "SOCIAL_POST", "platform": "小红书 / 朋友圈", "title": f"{weather_label}杭州：{profile['label']}值得住一晚", "content": social_post, "visual_brief": f"首图突出{partner_name}具体体验，后续展示房间、城市场景、时间卡和余量。", "call_to_action": "收藏这段杭州行程"},
                {"asset_type": "SHORT_VIDEO_SCRIPT", "platform": "短视频 30 秒", "title": f"30秒讲清{profile['label']}主题宿", "content": short_video, "visual_brief": "镜头必须出现房间、服务、体验现场和时间地点四类具体画面。", "call_to_action": "立即查看可售套餐"},
                {"asset_type": "STORE_CARD", "platform": "OTA / 酒店前台", "title": f"{profile['label']}产品卖点卡", "content": f"{weather_label}友好 · {room_name} · {service_names} · {partner_name}\n场次 {partner_time} · {partner_address}\n适合 {audience} · ¥{payload.get('preferred_price', '599')} / 套 · 余 {capacity} 个名额", "visual_brief": "用房间、服务、体验、场次四块信息替代大段宣传语。", "call_to_action": "查看详情"},
            ],
            "recommendation_reason": f"{room_name}、{service_names}和{partner_name}在{payload.get('target_date', '入住日')}可用，场次为{partner_time}。该组合同时满足{weather_label}、{audience}与真实容量约束，适合把{profile['label']}做成可直接销售的杭州旅居产品。",
            "risk_message": "体验名额、房量、天气和价格会实时变化；如有过敏、儿童安全或饮食禁忌，请在预约意向中说明并等待酒店与商户人工确认。",
        }

    @staticmethod
    def _visitor(payload: dict[str, Any]) -> dict[str, Any]:
        products = payload.get("products", [])
        target_ids = [item["id"] for item in products if item.get("sale_quantity", 0) > 0]
        allergy = payload.get("allergy_information", "")
        natural_language = str(payload.get("natural_language", "")).strip()
        negative = payload.get("negative_interests", []) or []
        needs_hint = f"我先按你的描述整理：{natural_language}。" if natural_language else ""
        question = str(payload.get("question", "")).strip()
        if question:
            answer = f"{needs_hint}关于“{question}”，我会优先依据当前套餐的真实场次、库存、天气和年龄范围回答；最终预约以酒店与商户确认结果为准。"
        elif target_ids:
            answer = f"{needs_hint}当前有{len(target_ids)}个套餐同时通过预算、人数、天气和库存校验。已排除你标记的不偏好：{'、'.join(negative) or '暂无'}，可以继续查看时间安排。"
        else:
            answer = f"{needs_hint}暂时没有同时满足这些条件的可售套餐，可以放宽日期、预算或体验偏好，我会继续按真实库存匹配。"
        return {
            "answer": answer,
            "safety_notes": "过敏、儿童安全和活动场次必须由酒店与商户在确认前再次人工核对，AI不会替代安全确认。",
            "selected_product_ids": target_ids,
            "reasons": {str(item["id"]): f"匹配预算、天气、同行客群和实时库存；同时考虑了负向偏好{'、'.join(negative)}。" for item in products if item["id"] in target_ids},
            "schedule_notes": {str(item["id"]): [{"time": "15:00", "title": "办理入住", "description": "酒店前台办理入住并领取体验时间卡"}, {"time": "16:00", "title": "前往体验", "description": "以产品详情中的真实场次与地址为准"}] for item in products if item["id"] in target_ids},
            "limited_adjustments": {str(item["id"]): ["可在预约意向中备注希望的场次与同行注意事项", "实时名额变化后以酒店与商户确认结果为准"] for item in products if item["id"] in target_ids},
            "allergy_warning": f"已记录过敏信息：{allergy}；酒店与商户需要在确认前再次核对。" if allergy else "如有过敏或饮食禁忌，请在预约意向中主动说明。",
        }
