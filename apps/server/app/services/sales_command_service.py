"""Natural-language sales control for the hotel workbench.

An operator sentence like "把亲子类的产品暂停销售" is mapped to a concrete
status change on the matching products, without any model inference: the verbs
and the category words are a closed vocabulary, so the result is auditable.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ..core.exceptions import AppError
from ..models import TravelProduct


PAUSE_WORDS = ("暂停", "停售", "下架", "停止销售", "关闭销售", "暂停销售")
RESUME_WORDS = ("恢复", "上架", "重新销售", "开售", "开启销售", "恢复销售")

# Category words an operator actually uses, mapped to the words that appear in
# a product name, theme or its resource names.
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "亲子家庭": ("亲子", "家庭", "孩子", "儿童"),
    "两人约会": ("两人", "双人", "情侣", "约会"),
    "朋友出行": ("朋友", "开黑", "聚会", "运动"),
    "独自旅行": ("一人", "独自", "一个人"),
    "本地周末": ("本地", "周末"),
    "夜游": ("夜游", "夜景", "夜晚", "夜场"),
    "博物馆看展": ("博物馆", "看展", "展览", "美术馆", "科技馆"),
    "旅拍": ("旅拍", "摄影", "拍照"),
    "美食": ("美食", "夜市", "咖啡", "甜品", "下午茶", "杭帮菜"),
    "运动体验": ("运动", "攀岩", "卡丁车", "射箭", "骑行"),
    "主题乐园": ("乐园", "游乐", "主题公园"),
    "演出剧场": ("演出", "剧场", "儿童剧", "音乐现场"),
    "自然户外": ("湿地", "自然", "湘湖", "西溪", "九溪", "户外"),
    "运河": ("运河", "拱宸桥"),
    "西湖": ("西湖", "湖滨"),
    "良渚": ("良渚",),
}


def _searchable(db: Session, product: TravelProduct) -> str:
    """Everything an operator could name when describing a product."""

    names = " ".join(str(getattr(row, "resource_name", "") or "") for row in product.resources)
    address = " ".join(str(getattr(row, "address", "") or "") for row in product.resources)
    return f"{product.product_name} {product.theme} {names} {address}".lower()


def apply_sales_command(db: Session, hotel_id: int, natural_language: str) -> dict[str, Any]:
    text = " ".join(str(natural_language or "").split())
    if len(text) < 2:
        raise AppError("VALIDATION_ERROR", "请说明要暂停还是恢复哪些产品。", field="natural_language")
    pause = any(word in text for word in PAUSE_WORDS)
    resume = any(word in text for word in RESUME_WORDS)
    if pause and resume:
        raise AppError("VALIDATION_ERROR", "一句话里同时出现了暂停和恢复，请分开说明。", field="natural_language")
    if not pause and not resume:
        raise AppError("VALIDATION_ERROR", "请说明是“暂停销售”还是“恢复销售”。", field="natural_language")
    target_status = "PAUSED" if pause else "ON_SALE"

    matched_labels = [label for label, words in CATEGORY_KEYWORDS.items() if any(word in text for word in words)]
    scope_words = {word for label in matched_labels for word in CATEGORY_KEYWORDS[label]}

    products = list(
        db.query(TravelProduct)
        .filter(TravelProduct.hotel_id == hotel_id, TravelProduct.status != "DELETED")
        .all()
    )
    affected: list[dict[str, Any]] = []
    expired_skipped = 0
    for product in products:
        haystack = _searchable(db, product)
        if scope_words and not any(word in haystack for word in scope_words):
            continue
        if not scope_words and "所有" not in text and "全部" not in text:
            raise AppError(
                "VALIDATION_ERROR",
                "没有识别到具体类别；请说明类别（例如“亲子”“夜游”）或使用“全部产品”。",
                field="natural_language",
            )
        if product.status == target_status:
            continue
        if resume and product.target_date < date.today():
            expired_skipped += 1
            continue
        previous = product.status
        product.status = target_status
        affected.append(
            {
                "id": product.id,
                "product_name": product.product_name,
                "from": previous,
                "to": target_status,
                "sale_quantity": int(product.sale_quantity or 0),
            }
        )
    db.flush()
    action_label = "暂停销售" if pause else "恢复销售"
    scope_label = "、".join(matched_labels) if matched_labels else "全部产品"
    return {
        "action": action_label,
        "scope": scope_label,
        "affected": affected,
        "message": (
            f"已{action_label} {len(affected)} 个产品（范围：{scope_label}）。"
            + (f"另有 {expired_skipped} 个产品已过出行日期，保持下架。" if expired_skipped else "")
            if affected
            else (
                f"{scope_label}没有需要变更的产品。"
                + (f"其中 {expired_skipped} 个已过出行日期，不能重新上架。" if expired_skipped else "")
            )
        ),
    }
