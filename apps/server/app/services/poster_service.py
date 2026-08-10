"""Deterministic, media-led SVG poster rendering.

The Agent supplies creative meaning; this module owns the safe layout and
turns a curated media record into a visual asset.  It never asks an Agent to
invent an image URL and never uses poster text truncation by character count.
"""

from __future__ import annotations

import base64
import html
from functools import lru_cache
from typing import Any

import httpx

from ..config import settings


MEDIA_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "themepark": (
        "https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1600&q=85",
        "https://images.pexels.com/photos/1779487/pexels-photo-1779487.jpeg?auto=compress&cs=tinysrgb&w=1600",
    ),
    "family": (
        "https://images.unsplash.com/photo-1511895426328-dc8714191300?auto=format&fit=crop&w=1600&q=85",
        "https://images.unsplash.com/photo-1503454537195-1dcabb73ffb9?auto=format&fit=crop&w=1600&q=85",
    ),
    "sport": (
        "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&w=1600&q=85",
        "https://images.pexels.com/photos/1699030/pexels-photo-1699030.jpeg?auto=compress&cs=tinysrgb&w=1600",
    ),
    "nightlife": (
        "https://images.unsplash.com/photo-1518005020951-eccb494ad742?auto=format&fit=crop&w=1600&q=85",
        "https://images.unsplash.com/photo-1519608487953-e999c86e7455?auto=format&fit=crop&w=1600&q=85",
    ),
    "photo": (
        "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=1600&q=85",
        "https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=1600&q=85",
    ),
    "food": (
        "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1600&q=85",
        "https://images.pexels.com/photos/262978/pexels-photo-262978.jpeg?auto=compress&cs=tinysrgb&w=1600",
    ),
    "nature": (
        "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=1600&q=85",
        "https://images.unsplash.com/photo-1473445361085-b9a07f55608b?auto=format&fit=crop&w=1600&q=85",
    ),
    "culture": (
        "https://images.unsplash.com/photo-1452860606245-08befc0ff44b?auto=format&fit=crop&w=1600&q=85",
        "https://images.unsplash.com/photo-1528698827591-e19ccd7bc23d?auto=format&fit=crop&w=1600&q=85",
    ),
    "tea": (
        "https://images.unsplash.com/photo-1544787219-7f47ccb76574?auto=format&fit=crop&w=1600&q=85",
        "https://images.unsplash.com/photo-1564890369478-c89ca6d9cde9?auto=format&fit=crop&w=1600&q=85",
    ),
    "city_walk": (
        "https://images.unsplash.com/photo-1480714378408-67cf0d13bc1b?auto=format&fit=crop&w=1600&q=85",
        "https://images.unsplash.com/photo-1511988617509-a57c8a288659?auto=format&fit=crop&w=1600&q=85",
    ),
}


def text_width(text: str, font_size: float) -> float:
    """Approximate rendered width for CJK plus mixed Latin text."""
    return sum(font_size if ord(char) > 255 else font_size * 0.56 for char in text)


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    latin = ""
    for char in str(text):
        if ord(char) <= 255 and (char.isalnum() or char in "-_/&"):
            latin += char
            continue
        if latin:
            tokens.append(latin)
            latin = ""
        if not char.isspace():
            tokens.append(char)
    if latin:
        tokens.append(latin)
    return tokens


def wrap_text(text: str, max_width: float, font_size: float, max_lines: int = 3, ellipsis: bool = True) -> list[str]:
    """Wrap CJK characters and Latin words within a measured safe width."""
    lines: list[str] = []
    current = ""
    for token in _tokens(text):
        candidate = f"{current}{token}" if not current or token in "，。！？、:：·" or len(token) == 1 else f"{current} {token}"
        if current and text_width(candidate, font_size) > max_width:
            lines.append(current.strip())
            current = token
        else:
            current = candidate
    if current.strip():
        lines.append(current.strip())
    if len(lines) <= max_lines:
        return lines
    lines = lines[:max_lines]
    if ellipsis:
        last = lines[-1]
        while last and text_width(f"{last}…", font_size) > max_width:
            last = last[:-1]
        lines[-1] = f"{last}…"
    return lines


def fit_lines(text: str, max_width: float, base_size: float, max_lines: int = 3) -> tuple[list[str], float]:
    for size in (base_size, base_size - 4, base_size - 8, base_size - 12):
        lines = wrap_text(text, max_width, size, max_lines=max_lines)
        if len(lines) <= max_lines and all(text_width(line, size) <= max_width for line in lines):
            return lines, size
    size = max(16, base_size - 12)
    return wrap_text(text, max_width, size, max_lines=max_lines), size


def _xml(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


@lru_cache(maxsize=64)
def _remote_data_uri(url: str) -> str | None:
    if not settings.poster_embed_remote_images or not url:
        return None
    allowed = ("images.unsplash.com", "images.pexels.com", "upload.wikimedia.org")
    if not any(host in url for host in allowed):
        return None
    try:
        response = httpx.get(url, timeout=min(settings.agent_timeout_seconds, 4))
        response.raise_for_status()
        content = response.content
        if len(content) > 360_000:
            return None
        mime = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            mime = "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
    except Exception:
        return None


def classify_poster(*parts: str, target_crowd: str = "") -> str:
    text = " ".join(parts).lower()
    aliases = (
        ("themepark", ("乐园", "游乐", "主题公园", "theme park")),
        ("sport", ("攀岩", "卡丁车", "运动", "sport")),
        ("nightlife", ("夜游", "夜景", "音乐", "夜生活", "night")),
        ("photo", ("旅拍", "摄影", "拍照", "photo")),
        ("food", ("美食", "杭帮菜", "甜品", "咖啡", "烘焙", "food")),
        ("nature", ("自然", "湿地", "动物", "植物", "nature")),
        ("culture", ("非遗", "手作", "文化", "craft")),
        ("tea", ("茶", "点茶", "茶园", "tea")),
    )
    for category, words in aliases:
        if any(word in text for word in words):
            if target_crowd == "FAMILY" and category in {"culture", "tea"}:
                return "family"
            return category
    if target_crowd == "COUPLE":
        return "photo"
    if target_crowd == "FRIENDS":
        return "sport"
    if target_crowd == "SOLO":
        return "city_walk"
    if target_crowd == "FAMILY":
        return "family"
    return "city_walk"


def select_media_url(category: str, seed: int = 0) -> str:
    items = MEDIA_BY_CATEGORY.get(category, MEDIA_BY_CATEGORY["city_walk"])
    return items[abs(seed) % len(items)]


def _text_block(text: str, x: int, y: int, width: int, size: int, fill: str, max_lines: int = 3, weight: int = 500, line_gap: int | None = None) -> str:
    lines, fitted = fit_lines(text, width, size, max_lines)
    gap = line_gap or int(fitted * 1.2)
    return "".join(f'<text x="{x}" y="{y + index * gap}" fill="{fill}" font-size="{fitted}" font-weight="{weight}" font-family="Arial, Microsoft YaHei, sans-serif">{_xml(line)}</text>' for index, line in enumerate(lines))


def render_poster_svg(*, title: str, subtitle: str, partner_name: str, room_name: str, address: str, price: str, target_crowd: str, theme: str, weather: str, variant_index: int = 0, media_url: str | None = None, media_data_uri: str | None = None, creative_angle: str = "") -> str:
    category = classify_poster(title, subtitle, partner_name, theme, target_crowd=target_crowd)
    palette = {
        "themepark": ("#ffb14e", "#173f39", "#fff2cf"), "family": ("#ef8d68", "#24695e", "#fff1d4"),
        "sport": ("#5c9ab0", "#173c55", "#e7f4f2"), "nightlife": ("#6670b8", "#15172f", "#e9e7ff"),
        "photo": ("#d7a17e", "#284e56", "#ffeadb"), "food": ("#cf794a", "#54372b", "#fff0dc"),
        "nature": ("#78a66d", "#245a50", "#eaf3df"), "culture": ("#d19b5d", "#174d46", "#f6e8ce"),
        "tea": ("#86a66d", "#365a48", "#eff3dc"), "city_walk": ("#80aaa4", "#21554f", "#e8f3ed"),
    }
    accent, dark, light = palette.get(category, palette["city_walk"])
    media = media_data_uri or _remote_data_uri(media_url or select_media_url(category, variant_index)) or media_url or select_media_url(category, variant_index)
    safe_media = _xml(media)
    title_lines, title_size = fit_lines(title, 820, 62, max_lines=3)
    title_svg = "".join(f'<text x="80" y="{735 + idx * int(title_size * 1.14)}" fill="{dark}" font-size="{title_size}" font-weight="750" font-family="Arial, Microsoft YaHei, sans-serif">{_xml(line)}</text>' for idx, line in enumerate(title_lines))
    meta = _text_block(f"{weather} · {target_crowd} · {partner_name}", 84, 855, 860, 24, dark, max_lines=2)
    details = _text_block(f"住进 {room_name}，把这段杭州内容放进今晚。{address}", 92, 1000, 830, 25, dark, max_lines=3)
    footer = _text_block(creative_angle or "真实场次 · 实时余量 · 到店后按时间卡体验", 92, 1145, 830, 21, "#627b73", max_lines=2)
    image = f'<image href="{safe_media}" x="60" y="128" width="960" height="560" preserveAspectRatio="xMidYMid slice" clip-path="url(#heroClip)"/>'
    art = {
        "themepark": '<path d="M110 650 Q270 490 430 650 T790 620" fill="none" stroke="#fff" stroke-width="16" opacity=".6"/>',
        "family": '<rect x="705" y="220" width="210" height="230" rx="26" fill="#fff" opacity=".25"/><circle cx="770" cy="325" r="34" fill="#fff" opacity=".7"/><circle cx="850" cy="325" r="34" fill="#fff" opacity=".7"/>',
        "sport": '<path d="M120 610 L300 270 L470 610" fill="none" stroke="#fff" stroke-width="20" stroke-linecap="round" opacity=".65"/>',
        "nightlife": '<circle cx="850" cy="245" r="68" fill="#f6d687" opacity=".8"/><path d="M700 620 Q810 470 930 620" fill="none" stroke="#fff" stroke-width="16" opacity=".6"/>',
        "photo": '<rect x="720" y="255" width="210" height="130" rx="16" fill="#fff" opacity=".5"/><circle cx="825" cy="320" r="40" fill="#284e56" opacity=".75"/>',
        "food": '<ellipse cx="820" cy="510" rx="150" ry="32" fill="#fff" opacity=".55"/><path d="M700 470 Q820 330 940 470" fill="#fff" opacity=".38"/>',
        "nature": '<path d="M720 600 Q820 400 930 600" fill="#fff" opacity=".4"/><path d="M820 600 V360 M820 450 Q750 400 710 450 M820 470 Q890 415 935 460" stroke="#245a50" stroke-width="13" fill="none"/>',
        "culture": '<path d="M720 530 l115 -155 l115 155" fill="none" stroke="#fff" stroke-width="15" opacity=".65"/><circle cx="835" cy="345" r="18" fill="#d45c53"/>',
        "tea": '<ellipse cx="820" cy="500" rx="130" ry="25" fill="#fff" opacity=".55"/><path d="M730 465 Q730 370 820 370 Q910 370 910 465" fill="#fff" opacity=".62"/>',
        "city_walk": '<path d="M690 590 Q800 470 930 590" fill="none" stroke="#fff" stroke-width="18" opacity=".6"/>',
    }[category]
    layout_class = f"{category}-layout-{variant_index % 3}"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440" data-layout="{layout_class}" data-category="{category}"><defs><clipPath id="heroClip"><rect x="60" y="128" width="960" height="560" rx="34"/></clipPath><linearGradient id="wash" x1="0" x2="1"><stop stop-color="{dark}" stop-opacity=".7"/><stop offset="1" stop-color="{dark}" stop-opacity=".08"/></linearGradient></defs><rect width="1080" height="1440" rx="36" fill="{light}"/><rect width="1080" height="730" fill="{dark}" opacity=".08"/><text x="72" y="90" fill="{dark}" font-size="26" font-weight="700" letter-spacing="4" font-family="Arial, Microsoft YaHei, sans-serif">STAYSCAPE · HANGZHOU</text>{image}<rect x="60" y="128" width="960" height="560" rx="34" fill="url(#wash)" opacity=".6"/><g>{art}</g>{title_svg}{meta}<rect x="70" y="925" width="940" height="220" rx="26" fill="#fff" opacity=".88"/>{details}{footer}<rect x="70" y="1190" width="370" height="145" rx="24" fill="{dark}"/><text x="105" y="1240" fill="#c9eadc" font-size="20" font-family="Arial, Microsoft YaHei, sans-serif">今晚起价</text><text x="105" y="1300" fill="#fff" font-size="52" font-weight="750" font-family="Arial, sans-serif">¥{_xml(price)}</text><rect x="470" y="1190" width="540" height="145" rx="24" fill="{accent}"/><text x="510" y="1250" fill="{dark}" font-size="23" font-weight="700" font-family="Arial, Microsoft YaHei, sans-serif">查看场次 · 提交预约意向</text><text x="510" y="1295" fill="{dark}" font-size="19" font-family="Arial, Microsoft YaHei, sans-serif">{_xml(category.upper())} · REAL-TIME STAY</text><text x="72" y="1380" fill="#627b73" font-size="20" font-family="Arial, Microsoft YaHei, sans-serif">#杭州旅行 #StayScape #{_xml(category)}</text></svg>'''


def poster_asset(*, title: str, content: str, partner_name: str, room_name: str, address: str, price: str, target_crowd: str, theme: str, weather: str, variant_index: int = 0, creative_angle: str = "") -> dict[str, str]:
    category = classify_poster(title, content, partner_name, theme, target_crowd=target_crowd)
    return {"poster_svg": render_poster_svg(title=title, subtitle=content, partner_name=partner_name, room_name=room_name, address=address, price=price, target_crowd=target_crowd, theme=theme, weather=weather, variant_index=variant_index, creative_angle=creative_angle), "poster_style": f"{category}-layout-{variant_index % 3}", "creative_angle": creative_angle or f"{category}主题主视觉"}
