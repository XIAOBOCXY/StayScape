"""Public-facing travel copy guardrails.

The operator console can contain operational data.  Visitor endpoints use these
helpers so generated text stays warm, useful and free of internal jargon.
"""

from __future__ import annotations

import re
from typing import Any

from .serializers import product_to_dict

_INTERNAL_LANGUAGE = re.compile(
    r"(?:库存|房量|成本|售价|毛利|规则引擎|容量约束|真实容量|实时余量|固定场次|"
    r"可直接销售|确定性|履约|供给|产品草稿|酒店服务|实时计算|校验|Demo|Mock|"
    r"Skill|Agent|trace[_ -]?id)",
    re.IGNORECASE,
)
_SENTENCES = re.compile(r"[^。！？!?]+[。！？!?]?")


def public_travel_copy(value: object, fallback: str = "") -> str:
    """Remove operational sentences from text returned to a traveller."""

    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return fallback
    kept = [
        sentence.strip()
        for sentence in _SENTENCES.findall(text)
        if sentence.strip() and not _INTERNAL_LANGUAGE.search(sentence)
    ]
    result = "".join(kept).strip()
    return result if len(result) >= 6 else fallback


def visitor_product_to_dict(product: Any) -> dict[str, Any]:
    """Serialize a product for the public site without operator-only language."""

    data = product_to_dict(product)
    theme = str(data.get("theme") or "杭州周末")
    crowd = {"FAMILY": "亲子家庭", "COUPLE": "两人同行", "FRIENDS": "朋友出行", "SOLO": "独自旅行", "LOCAL_WEEKEND": "本地周末客"}.get(str(data.get("target_crowd") or ""), "旅人")
    title_fallback = f"{theme}，给{crowd}的一段杭州时光。"
    story_fallback = f"住进杭州，慢慢体验{theme}，把今天留给真正想去的地方。"
    reason_fallback = f"围绕{theme}安排住宿与在地玩法，适合轻松度过一段杭州时间。"

    data["marketing_title"] = public_travel_copy(data.get("marketing_title"), title_fallback)
    data["marketing_content"] = public_travel_copy(data.get("marketing_content"), story_fallback)
    data["recommendation_reason"] = public_travel_copy(data.get("recommendation_reason"), reason_fallback)
    data["risk_message"] = public_travel_copy(
        data.get("risk_message"),
        "如有饮食、儿童陪同或行动安排方面的需求，提交预约意向时告诉我们即可。",
    )

    for resource in data.get("resources") or []:
        resource["description"] = public_travel_copy(
            resource.get("description"),
            "把这段体验慢慢安排进你的杭州行程。",
        )

    assets: list[dict[str, Any]] = []
    for raw_asset in data.get("marketing_assets") or []:
        asset = dict(raw_asset)
        for key in ("title", "content", "visual_brief", "creative_angle", "call_to_action"):
            if key in asset:
                asset[key] = public_travel_copy(asset.get(key), "")
        poster_svg = str(asset.get("poster_svg") or "")
        if poster_svg and not poster_svg.lstrip().lower().startswith("<svg"):
            asset["poster_svg"] = ""
        elif _INTERNAL_LANGUAGE.search(poster_svg):
            asset["poster_svg"] = _INTERNAL_LANGUAGE.sub("杭州旅居", poster_svg)
        assets.append(asset)
    data["marketing_assets"] = assets
    return data
