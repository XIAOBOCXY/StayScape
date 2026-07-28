from datetime import time

from ..core.exceptions import AppError


def intervals_overlap(start_a: time | None, end_a: time | None, start_b: time | None, end_b: time | None) -> bool:
    if not all((start_a, end_a, start_b, end_b)):
        return False
    return max(start_a, start_b) < min(end_a, end_b)


def validate_interval(start: time | None, end: time | None, field: str) -> None:
    if start and end and start >= end:
        raise AppError("TIME_INVALID", "活动开始时间必须早于结束时间", field=field)

