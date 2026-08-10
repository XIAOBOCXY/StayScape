from datetime import date
from typing import Any

from ..core.exceptions import AppError


def tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip().upper() for part in value.replace("，", ",").split(",") if part.strip()}


def resource_is_usable(*, merchant_status: str, package_enabled: bool, resource_status: str, capacity: int, source_type: str = "PARTNER") -> bool:
    """Return whether a partner resource is legal for a sellable package.

    PUBLIC_REFERENCE rows are useful for visitor inspiration but intentionally
    cannot enter the commercial product pool. DEMO rows represent the
    competition's simulated partner inventory and are explicitly allowed.
    """
    return (
        merchant_status == "ACTIVE"
        and source_type.upper() in {"PARTNER", "DEMO"}
        and package_enabled
        and resource_status == "AVAILABLE"
        and capacity > 0
    )


def check_date(actual: date, target: date, field: str) -> None:
    if actual != target:
        raise AppError("DATE_NOT_MATCHED", "资源日期与入住日期不一致", field=field, retryable=True)


def check_non_negative(value: int, field: str) -> None:
    if value < 0:
        raise AppError("VALIDATION_ERROR", "库存或名额不能为负数", field=field)
