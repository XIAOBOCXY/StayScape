"""Product-specific, share-ready SVG poster rendering.

The Agent creates the creative copy through the API; this renderer composes a
standalone 1080×1440 poster from the real product data. Optional Wan images are
embedded into the SVG so a downloaded poster keeps its visual after sharing.
"""

from __future__ import annotations

import base64
import html
import mimetypes
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from ..config import settings


MEDIA_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "themepark": (
        "https://youimg1.c-ctrip.com/target/100q040000000b7qhD3B1.jpg",
        "https://images.pexels.com/photos/1779487/pexels-photo-1779487.jpeg?auto=compress&cs=tinysrgb&w=1600",
    ),
    "family": (
        "https://images.unsplash.com/photo-1511895426328-dc8714191300?auto=format&fit=crop&w=1600&q=85",
        "https://images.unsplash.com/photo-1503454537195-1dcabb73ffb9?auto=format&fit=crop&w=1600&q=85",
    ),
    "sport": (
        "https://images.pexels.com/photos/1699030/pexels-photo-1699030.jpeg?auto=compress&cs=tinysrgb&w=1600",
        "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&w=1600&q=85",
    ),
    "nightlife": (
        "https://commons.wikimedia.org/wiki/Special:FilePath/20231122%20Gongchen%20Bridge%2002.jpg?width=1600",
        "https://commons.wikimedia.org/wiki/Special:FilePath/West%20Lake%2C%20Hangzhou%202025.jpg?width=1600",
    ),
    "photo": (
        "https://commons.wikimedia.org/wiki/Special:FilePath/West%20Lake%2C%20Hangzhou.jpg?width=1600",
        "https://commons.wikimedia.org/wiki/Special:FilePath/20231122%20Gongchen%20Bridge%2002.jpg?width=1600",
    ),
    "food": (
        "https://images.pexels.com/photos/262978/pexels-photo-262978.jpeg?auto=compress&cs=tinysrgb&w=1600",
        "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1600&q=85",
    ),
    "nature": (
        "https://commons.wikimedia.org/wiki/Special:FilePath/Xixi%20Wetland%20Park%2C%20Hangzhou%2C%E6%9D%AD%E5%B7%9E%E8%A5%BF%E6%BA%AA%E6%B9%BF%E5%9C%B0%20-%20panoramio.jpg?width=1600",
        "https://commons.wikimedia.org/wiki/Special:FilePath/Tea%20Garden%20Hangzhou.jpg?width=1600",
    ),
    "museum": (
        "https://zh.unesco.org/silkroad/sites/default/files/styles/silkroad_colorbox/public/museum_front.jpg?itok=y1whLB1I",
        "https://p2.img.cctvpic.com/photoworkspace/contentimg/2025/02/07/2025020710435689379.jpg",
        "https://commons.wikimedia.org/wiki/Special:FilePath/Liangzhu%20Museum%2C%202019-07-07%2009.jpg?width=1600",
    ),
    "culture": (
        "https://commons.wikimedia.org/wiki/Special:FilePath/Lingyin%20Buddhist%20Temple%2C%20Hangzhou%20%283020083374%29.jpg?width=1600",
        "https://commons.wikimedia.org/wiki/Special:FilePath/Liangzhu%20Museum%2C%202019-07-07%2009.jpg?width=1600",
    ),
    "tea": (
        "https://commons.wikimedia.org/wiki/Special:FilePath/Tea%20Garden%20Hangzhou.jpg?width=1600",
        "https://commons.wikimedia.org/wiki/Special:FilePath/Longjing%20tea%20village%20Hangzhou.jpg?width=1600",
    ),
    "city_walk": (
        "https://commons.wikimedia.org/wiki/Special:FilePath/West%20Lake%2C%20Hangzhou%202025.jpg?width=1600",
        "https://commons.wikimedia.org/wiki/Special:FilePath/20231122%20Gongchen%20Bridge%2002.jpg?width=1600",
    ),
}

_CATEGORY_LABEL = {
    "themepark": "玩乐周末", "family": "亲子探索", "sport": "活力出发",
    "nightlife": "城市夜游", "photo": "约会漫游", "food": "美食小聚",
    "nature": "自然放空", "museum": "城市看展", "culture": "人文体验",
    "tea": "慢慢喝茶", "city_walk": "杭州漫游",
}
_CROWD_LABEL = {
    "FAMILY": "亲子家庭", "COUPLE": "两人出发", "FRIENDS": "朋友相聚",
    "SOLO": "一个人慢游", "LOCAL_WEEKEND": "本地周末",
}
_PALETTES = {
    "themepark": ("#F37C57", "#3A1E33", "#FFF2E7"),
    "family": ("#E96F63", "#203F52", "#FFF0DD"),
    "sport": ("#3E91A6", "#173A55", "#E8F5F2"),
    "nightlife": ("#7B6FC9", "#241F47", "#EFECFF"),
    "photo": ("#C87C64", "#4C2933", "#FCECE4"),
    "food": ("#C66B44", "#4C3026", "#FFF0E7"),
    "nature": ("#5D9B7B", "#204C45", "#E7F3E7"),
    "museum": ("#AC8554", "#3E352A", "#F7EFE1"),
    "culture": ("#B87948", "#3E3F31", "#F8EFDC"),
    "tea": ("#76905B", "#35483C", "#F0F5E7"),
    "city_walk": ("#4E998D", "#163D42", "#E7F3F1"),
}
_ALLOWED_REMOTE_HOSTS = {
    "images.unsplash.com", "images.pexels.com", "upload.wikimedia.org",
    "commons.wikimedia.org", "zh.unesco.org", "p2.img.cctvpic.com",
    "youimg1.c-ctrip.com", "obj.shine.cn",
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
        candidate = f"{current}{token}" if not current or token in "，。！？、: ：·" or len(token) == 1 else f"{current} {token}"
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


def _data_uri(content: bytes, mime: str) -> str | None:
    if not content or len(content) > 720_000:
        return None
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        return None
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def _local_media_data_uri(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    path = unquote(parsed.path or url)
    prefix = settings.generated_media_url_path.rstrip("/")
    if not path.startswith(f"{prefix}/"):
        return None
    relative = path[len(prefix) + 1 :]
    if not relative or "/" in relative or "\\" in relative:
        return None
    root = Path(settings.generated_media_dir).resolve()
    candidate = (root / relative).resolve()
    if candidate.parent != root or not candidate.is_file():
        return None
    mime = mimetypes.guess_type(candidate.name)[0] or "image/jpeg"
    try:
        return _data_uri(candidate.read_bytes(), mime)
    except OSError:
        return None


@lru_cache(maxsize=64)
def _remote_data_uri(url: str) -> str | None:
    if not settings.poster_embed_remote_images or not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    if host not in _ALLOWED_REMOTE_HOSTS:
        return None
    try:
        response = httpx.get(url, timeout=min(settings.agent_timeout_seconds, 5), follow_redirects=True)
        response.raise_for_status()
        mime = response.headers.get("content-type", "image/jpeg").split(";", 1)[0].lower()
        return _data_uri(response.content, mime)
    except httpx.HTTPError:
        return None


def classify_poster(*parts: str, target_crowd: str = "") -> str:
    text = " ".join(parts).lower()
    aliases = (
        ("themepark", ("乐园", "游乐", "主题公园", "theme park")),
        ("sport", ("攀岩", "卡丁车", "运动", "sport")),
        ("nightlife", ("夜游", "夜景", "音乐", "夜生活", "night")),
        ("photo", ("旅拍", "摄影", "拍照", "photo")),
        ("food", ("美食", "杭帮菜", "甜品", "咖啡", "烘焙", "food")),
        ("nature", ("自然", "湿地", "动物", "植物", "湘湖", "骑行", "nature")),
        ("museum", ("博物馆", "良渚", "看展", "美术馆", "科技馆", "展览", "museum")),
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
    gap = line_gap or int(fitted * 1.25)
    return "".join(
        f'<text x="{x}" y="{y + index * gap}" fill="{fill}" font-size="{fitted}" font-weight="{weight}" font-family="Inter, Arial, Microsoft YaHei, sans-serif">{_xml(line)}</text>'
        for index, line in enumerate(lines)
    )


def _decorative_art(category: str, accent: str, light: str, variant_index: int) -> str:
    offset = (variant_index % 3) * 24
    icons = {
        "themepark": f'<path d="M85 650 C210 490 360 715 510 550 S800 580 1000 410" fill="none" stroke="{light}" stroke-width="18" opacity=".48"/><circle cx="{790 + offset}" cy="255" r="72" fill="{accent}" opacity=".55"/>',
        "family": f'<circle cx="{805 + offset}" cy="265" r="54" fill="{light}" opacity=".55"/><circle cx="{900 - offset}" cy="345" r="86" fill="{accent}" opacity=".5"/>',
        "sport": f'<path d="M700 590 L820 240 L960 590" fill="none" stroke="{light}" stroke-width="18" stroke-linecap="round" opacity=".54"/>',
        "nightlife": f'<circle cx="{850 + offset}" cy="260" r="84" fill="{light}" opacity=".58"/><path d="M680 590 Q820 420 990 590" fill="none" stroke="{accent}" stroke-width="16" opacity=".7"/>',
        "photo": f'<rect x="710" y="260" width="230" height="145" rx="24" fill="{light}" opacity=".42"/><circle cx="825" cy="332" r="44" fill="{accent}" opacity=".78"/>',
        "food": f'<ellipse cx="820" cy="535" rx="160" ry="36" fill="{light}" opacity=".48"/><path d="M700 500 Q820 340 940 500" fill="{light}" opacity=".25"/>',
        "nature": f'<path d="M710 620 Q820 370 960 620" fill="{accent}" opacity=".52"/><path d="M820 605 V370 M820 450 Q760 390 700 445 M820 480 Q895 400 960 465" stroke="{light}" stroke-width="14" fill="none" opacity=".7"/>',
        "museum": f'<rect x="720" y="285" width="220" height="260" rx="20" fill="{light}" opacity=".35"/><path d="M742 365 H918 M770 365 V530 M820 365 V530 M870 365 V530" stroke="{accent}" stroke-width="14" opacity=".75"/>',
        "culture": f'<path d="M710 560 L825 370 L945 560" fill="none" stroke="{light}" stroke-width="18" opacity=".6"/><circle cx="825" cy="335" r="22" fill="{accent}" opacity=".9"/>',
        "tea": f'<ellipse cx="820" cy="505" rx="145" ry="28" fill="{light}" opacity=".5"/><path d="M720 470 Q720 365 820 365 Q920 370 920 470" fill="{light}" opacity=".48"/>',
        "city_walk": f'<path d="M670 590 Q810 430 990 590" fill="none" stroke="{light}" stroke-width="18" opacity=".55"/><circle cx="{825 + offset}" cy="315" r="38" fill="{accent}" opacity=".75"/>',
    }
    return icons[category]


def _date_label(value: str) -> str:
    normalized = str(value or "").replace("-", ".")
    return normalized if normalized else "杭州周末"


def render_poster_svg(
    *,
    title: str,
    subtitle: str,
    partner_name: str,
    room_name: str,
    address: str,
    price: str,
    target_crowd: str,
    theme: str,
    weather: str,
    target_date: str = "",
    variant_index: int = 0,
    media_url: str | None = None,
    media_data_uri: str | None = None,
    creative_angle: str = "",
) -> str:
    """Render a standalone share card with a product-specific visual hierarchy."""
    category = classify_poster(title, subtitle, partner_name, theme, target_crowd=target_crowd)
    accent, ink, paper = _PALETTES.get(category, _PALETTES["city_walk"])
    chosen_url = media_url or select_media_url(category, variant_index)
    media = media_data_uri or _local_media_data_uri(chosen_url) or _remote_data_uri(chosen_url)
    image_svg = (
        f'<image href="{_xml(media)}" x="44" y="126" width="992" height="622" preserveAspectRatio="xMidYMid slice" clip-path="url(#heroClip)"/>'
        if media else ""
    )
    title_lines, title_size = fit_lines(title, 832, 66, max_lines=2)
    title_svg = "".join(
        f'<text x="80" y="{846 + index * int(title_size * 1.17)}" fill="{ink}" font-size="{title_size}" font-weight="760" font-family="Inter, Arial, Microsoft YaHei, sans-serif">{_xml(line)}</text>'
        for index, line in enumerate(title_lines)
    )
    crowd = _CROWD_LABEL.get(target_crowd, "杭州周末")
    category_label = _CATEGORY_LABEL.get(category, "杭州漫游")
    experience = _text_block(f"{room_name} · {partner_name}", 82, 1035, 840, 24, ink, max_lines=1, weight=680)
    story = _text_block(subtitle or creative_angle or f"把这一晚和{partner_name}留给自己。", 82, 1118, 820, 24, "#5D6B68", max_lines=2, weight=430, line_gap=34)
    address_line = _text_block(address or "杭州", 82, 1245, 560, 18, "#7B8986", max_lines=1, weight=500)
    art = _decorative_art(category, accent, paper, variant_index)
    style = f"{category}-publish-{variant_index % 3}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440" data-layout="{style}" data-category="{category}">
  <defs>
    <clipPath id="heroClip"><rect x="44" y="126" width="992" height="622" rx="42"/></clipPath>
    <linearGradient id="heroShade" x1="0" y1="0" x2="0.92" y2="1"><stop stop-color="{ink}" stop-opacity=".72"/><stop offset=".48" stop-color="{ink}" stop-opacity=".16"/><stop offset="1" stop-color="{ink}" stop-opacity=".58"/></linearGradient>
    <linearGradient id="paperGlow" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fff" stop-opacity=".72"/><stop offset="1" stop-color="{paper}" stop-opacity="0"/></linearGradient>
  </defs>
  <rect width="1080" height="1440" rx="42" fill="{paper}"/>
  <circle cx="990" cy="80" r="210" fill="{accent}" opacity=".12"/>
  <circle cx="74" cy="1370" r="240" fill="{accent}" opacity=".08"/>
  <text x="74" y="76" fill="{ink}" font-size="24" font-weight="760" letter-spacing="3" font-family="Inter, Arial, Microsoft YaHei, sans-serif">杭州旅居 · 周末提案</text>
  <text x="1006" y="76" text-anchor="end" fill="{ink}" font-size="20" font-weight="650" font-family="Inter, Arial, Microsoft YaHei, sans-serif">{_xml(_date_label(target_date))}</text>
  <rect x="44" y="126" width="992" height="622" rx="42" fill="{ink}"/>
  {image_svg}
  <rect x="44" y="126" width="992" height="622" rx="42" fill="url(#heroShade)"/>
  <g>{art}</g>
  <rect x="82" y="170" width="156" height="48" rx="24" fill="#fff" opacity=".9"/>
  <text x="160" y="202" text-anchor="middle" fill="{ink}" font-size="20" font-weight="720" font-family="Inter, Arial, Microsoft YaHei, sans-serif">{_xml(category_label)}</text>
  <rect x="82" y="658" width="236" height="48" rx="24" fill="#111" opacity=".34"/>
  <text x="200" y="690" text-anchor="middle" fill="#fff" font-size="19" font-weight="650" font-family="Inter, Arial, Microsoft YaHei, sans-serif">{_xml(crowd)}</text>
  <rect x="744" y="658" width="252" height="48" rx="24" fill="{accent}" opacity=".96"/>
  <text x="870" y="690" text-anchor="middle" fill="{ink}" font-size="19" font-weight="760" font-family="Inter, Arial, Microsoft YaHei, sans-serif">杭州 · 一晚一游</text>
  <rect x="58" y="778" width="964" height="500" rx="38" fill="#fff"/>
  <rect x="58" y="778" width="964" height="500" rx="38" fill="url(#paperGlow)"/>
  {title_svg}
  <rect x="80" y="968" width="114" height="6" rx="3" fill="{accent}"/>
  {experience}
  {story}
  {address_line}
  <rect x="80" y="1306" width="920" height="1" fill="{ink}" opacity=".13"/>
  <text x="82" y="1362" fill="{ink}" font-size="20" font-weight="670" font-family="Inter, Arial, Microsoft YaHei, sans-serif">收藏这个周末</text>
  <text x="82" y="1397" fill="#788683" font-size="17" font-family="Inter, Arial, Microsoft YaHei, sans-serif">#杭州旅行  #{_xml(category_label)}  #周末灵感</text>
  <rect x="790" y="1330" width="210" height="72" rx="24" fill="{ink}"/>
  <text x="816" y="1357" fill="#DCEAE5" font-size="16" font-family="Inter, Arial, Microsoft YaHei, sans-serif">套餐参考价</text>
  <text x="816" y="1388" fill="#fff" font-size="30" font-weight="760" font-family="Inter, Arial, Microsoft YaHei, sans-serif">¥{_xml(price)}</text>
</svg>"""


def poster_asset(
    *,
    title: str,
    content: str,
    partner_name: str,
    room_name: str,
    address: str,
    price: str,
    target_crowd: str,
    theme: str,
    weather: str,
    target_date: str = "",
    variant_index: int = 0,
    creative_angle: str = "",
    media_url: str | None = None,
) -> dict[str, str]:
    category = classify_poster(title, content, partner_name, theme, target_crowd=target_crowd)
    return {
        "poster_svg": render_poster_svg(
            title=title,
            subtitle=content,
            partner_name=partner_name,
            room_name=room_name,
            address=address,
            price=price,
            target_crowd=target_crowd,
            theme=theme,
            weather=weather,
            target_date=target_date,
            variant_index=variant_index,
            creative_angle=creative_angle,
            media_url=media_url,
        ),
        "poster_style": f"{category}-publish-{variant_index % 3}",
        "creative_angle": creative_angle or f"{_CATEGORY_LABEL.get(category, '杭州漫游')}主视觉",
    }
