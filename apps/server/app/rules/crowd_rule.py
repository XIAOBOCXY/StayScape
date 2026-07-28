from ..core.exceptions import AppError
from .availability_rule import tokens


def crowd_supported(suitable_crowds: str | None, target_crowd: str, child_ages: list[int] | None = None, minimum_age: int | None = None, maximum_age: int | None = None) -> bool:
    crowd_tokens = tokens(suitable_crowds)
    target = (target_crowd or "ALL").upper()
    if crowd_tokens and "ALL" not in crowd_tokens and target not in crowd_tokens:
        return False
    ages = child_ages or []
    if minimum_age is not None and any(age < minimum_age for age in ages):
        return False
    if maximum_age is not None and any(age > maximum_age for age in ages):
        return False
    return True


def validate_crowd(*, suitable_crowds: str, target_crowd: str, resource_name: str, child_ages: list[int] | None = None, minimum_age: int | None = None, maximum_age: int | None = None) -> None:
    if not crowd_supported(suitable_crowds, target_crowd, child_ages, minimum_age, maximum_age):
        if child_ages and minimum_age is not None and any(age < minimum_age for age in child_ages):
            raise AppError("AGE_NOT_SUPPORTED", f"{resource_name}不适合当前儿童年龄", field="child_ages", retryable=True)
        raise AppError("CROWD_NOT_SUPPORTED", f"{resource_name}不适合当前目标客群", field="target_crowd", retryable=True)

