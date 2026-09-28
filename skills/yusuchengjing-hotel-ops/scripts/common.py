"""Shared, standard-library-only helpers for the portable 余宿成景 Skill."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# A portable Skill should emit UTF-8 JSON even when launched from a legacy
# Windows console.  Linux/OpenClaw runs already use UTF-8; reconfigure is a
# no-op where it is unavailable.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


class ToolFailure(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def as_decimal(value: Any, field: str) -> Decimal:
    if value is None or value == "":
        raise ToolFailure("MISSING_REQUIRED_DATA", f"缺少 {field}", {"field": field})
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ToolFailure("MISSING_REQUIRED_DATA", f"{field} 不是有效数值", {"field": field}) from exc


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def rate(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def data_path(name: str) -> Path:
    path = DATA_DIR / name
    if not path.exists():
        raise ToolFailure("DATA_FILE_NOT_FOUND", f"找不到数据文件 {name}", {"file": name})
    return path


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise ToolFailure("DATA_FILE_NOT_FOUND", f"找不到数据文件 {path}", {"file": str(path)}) from exc
    except json.JSONDecodeError as exc:
        raise ToolFailure("INVALID_JSON", f"数据文件不是有效 JSON：{path}", {"file": str(path), "line": exc.lineno}) from exc
    if not isinstance(value, dict):
        raise ToolFailure("INVALID_JSON", f"数据文件根节点必须是对象：{path}", {"file": str(path)})
    return value


def parse_json_input(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ToolFailure("INVALID_JSON", "--input 必须是 JSON 对象", {"line": exc.lineno}) from exc
    if not isinstance(parsed, dict):
        raise ToolFailure("INVALID_JSON", "--input 必须是 JSON 对象")
    return parsed


def parse_date(value: Any, field: str = "date") -> date:
    if not value:
        raise ToolFailure("MISSING_REQUIRED_DATA", f"缺少 {field}", {"field": field})
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ToolFailure("MISSING_REQUIRED_DATA", f"{field} 必须为 YYYY-MM-DD", {"field": field, "value": value}) from exc


def parse_window(value: str, field: str = "time_window") -> tuple[time, time]:
    if not value or "-" not in value:
        raise ToolFailure("MISSING_REQUIRED_DATA", f"{field} 必须为 HH:MM-HH:MM", {"field": field, "value": value})
    start_text, end_text = value.split("-", 1)
    try:
        start, end = time.fromisoformat(start_text), time.fromisoformat(end_text)
    except ValueError as exc:
        raise ToolFailure("MISSING_REQUIRED_DATA", f"{field} 必须为 HH:MM-HH:MM", {"field": field, "value": value}) from exc
    if start >= end:
        raise ToolFailure("TIME_CONFLICT", f"{field} 的开始时间必须早于结束时间", {"field": field, "value": value})
    return start, end


def windows_overlap(left: str, right: str) -> bool:
    left_start, left_end = parse_window(left)
    right_start, right_end = parse_window(right)
    return left_start < right_end and right_start < left_end


def weather_matches(tags: list[str], weather: str) -> bool:
    return str(weather).strip() in {str(item).strip() for item in tags}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def run_cli(handler: Callable[[], dict[str, Any]]) -> None:
    try:
        payload = handler()
        payload.setdefault("ok", True)
        emit(payload)
    except ToolFailure as exc:
        emit({"ok": False, "error_code": exc.code, "message": exc.message, "details": exc.details})
    except Exception as exc:  # Never leak a traceback to an Agent.
        emit({"ok": False, "error_code": "INTERNAL_TOOL_ERROR", "message": "确定性工具执行失败", "details": {"type": type(exc).__name__}})


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
