"""Small, explainable natural-language parser for the merchant product studio.

This deliberately does not create products or choose inventory.  It turns an
operator's sentence into editable draft fields; the existing inventory rules
remain the only source of executable room and partner selections.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any


_CROWD_RULES = (
    ("FAMILY", ("亲子", "孩子", "儿童", "小朋友", "一家", "家庭")),
    ("COUPLE", ("情侣", "约会", "两人", "两个人", "夫妻")),
    ("FRIENDS", ("朋友", "同学", "闺蜜", "同事", "室友")),
    ("SOLO", ("一个人", "独自", "solo", "自己去")),
    ("LOCAL_WEEKEND", ("本地", "周末微度假", "周末放松")),
)

_THEME_RULES = (
    ("博物馆看展", ("博物馆", "看展", "美术馆", "良渚", "丝绸")),
    ("乐园玩乐", ("乐园", "游乐", "主题公园", "宋城")),
    ("城市演出夜游", ("演出", "音乐", "夜游", "夜景", "剧场")),
    ("轻运动挑战", ("攀岩", "卡丁车", "运动", "射箭")),
    ("杭州美食小聚", ("美食", "咖啡", "甜品", "烘焙", "杭帮菜")),
    ("自然观察慢游", ("湿地", "自然", "徒步", "骑行", "湘湖")),
    ("人文手作体验", ("手作", "非遗", "陶艺", "文化")),
    ("湖畔城市漫游", ("西湖", "运河", "漫游", "拍照", "旅拍")),
    ("茶园慢慢放空", ("龙井", "茶园", "点茶", "茶文化")),
)

_CHINESE_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _weekday(text: str, today: date) -> date | None:
    if "周末" in text:
        days = (5 - today.weekday()) % 7 or 7
        return today + timedelta(days=days)
    matched = re.search(r"(?:周|星期)([一二三四五六日天])", text)
    if not matched:
        return None
    index = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}[matched.group(1)]
    return today + timedelta(days=(index - today.weekday()) % 7 or 7)


def _date_value(text: str, today: date) -> date | None:
    iso = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    month_day = re.search(r"(\d{1,2})月(\d{1,2})[日号]?", text)
    if month_day:
        try:
            result = date(today.year, int(month_day.group(1)), int(month_day.group(2)))
            return result if result >= today - timedelta(days=1) else date(today.year + 1, result.month, result.day)
        except ValueError:
            return None
    if "明天" in text:
        return today + timedelta(days=1)
    if "后天" in text:
        return today + timedelta(days=2)
    return _weekday(text, today)


def _money(text: str) -> Decimal | None:
    matched = re.search(r"(?:预算|售价|定价|控制在|不超过|¥|￥)[^0-9]{0,8}(\d{3,5})", text)
    return Decimal(matched.group(1)) if matched else None


def _party_size(text: str, crowd: str) -> int:
    """Extract a sellable group size without guessing from a theme word."""

    normalized = text.replace(" ", "")
    if any(token in normalized for token in ("两大两小", "2大2小", "二大二小")):
        return 4
    if any(token in normalized for token in ("两大一小", "2大1小", "二大一小")):
        return 3
    family = re.search(r"一家([一二两三四五六七八九十\d]+)口", normalized)
    if family:
        raw = family.group(1)
        value = int(raw) if raw.isdigit() else _CHINESE_DIGITS.get(raw, 3)
        return max(1, min(value, 12))
    people = re.search(r"([一二两三四五六七八九十\d]+)\s*(?:人|位)", normalized)
    if people:
        raw = people.group(1)
        value = int(raw) if raw.isdigit() else _CHINESE_DIGITS.get(raw, 3)
        return max(1, min(value, 12))
    return {"FAMILY": 3, "COUPLE": 2, "FRIENDS": 4, "SOLO": 1, "LOCAL_WEEKEND": 2}.get(crowd, 2)


def interpret_product_draft(natural_language: str, *, today: date | None = None) -> dict[str, Any]:
    """Return only UI-editable draft hints and a transparent parse summary."""

    text = natural_language.strip()
    now = today or date.today()
    crowd = next((value for value, words in _CROWD_RULES if any(word in text for word in words)), "FAMILY")
    party_size = _party_size(text, crowd)
    theme = next((value for value, words in _THEME_RULES if any(word in text for word in words)), "杭州周末体验")
    weather = "RAIN" if any(word in text for word in ("下雨", "雨天", "雨", "室内")) else "SUNNY" if "晴" in text else "CLOUDY"
    budget = _money(text) or Decimal("699")
    # “做两套亲子方案” is the common operator phrasing.  Do not treat “一个
    # 孩子” as a request for one candidate: bare 个 must still be followed by
    # a product noun, whereas bare 套 is unambiguous in this workflow.
    variants = re.search(
        r"([1-5一二两三四五])\s*(?:套(?:\s*(?:方案|产品|候选))?|个\s*(?:方案|产品|候选)|(?:方案|产品|候选))",
        text,
    )
    if variants:
        raw_variant_count = variants.group(1)
        variant_count = int(raw_variant_count) if raw_variant_count.isdigit() else _CHINESE_DIGITS.get(raw_variant_count, 3)
    else:
        variant_count = 3
    updates = {
        "target_date": (_date_value(text, now) or now + timedelta(days=1)).isoformat(),
        "target_crowd": crowd,
        "party_size": party_size,
        "weather": weather,
        "theme": theme,
        "visitor_budget": str(budget),
        "preferred_price": str(budget),
        "variant_count": variant_count,
        "creative_direction": text,
    }
    labels = {
        "target_date": "日期", "target_crowd": "同行人", "party_size": "套餐人数", "weather": "体验场景",
        "theme": "主题", "visitor_budget": "预算", "variant_count": "方案数量",
    }
    parsed = [{"field": key, "label": labels[key], "value": value} for key, value in updates.items() if key in labels]
    return {"interpreted": updates, "parsed_fields": parsed, "message": "已从一句话中提取偏好；库存与资源仍可在下方手动确认。"}
