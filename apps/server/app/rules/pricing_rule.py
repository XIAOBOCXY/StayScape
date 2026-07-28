from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from ..core.exceptions import AppError

MONEY = Decimal("0.01")


@dataclass(frozen=True)
class PricingResult:
    unit_cost: Decimal
    minimum_allowed_price: Decimal
    suggested_price: Decimal
    gross_profit: Decimal
    gross_margin: Decimal


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def calculate_pricing(
    *,
    unit_cost: Decimal,
    room_minimum_price: Decimal,
    minimum_gross_margin: Decimal,
    visitor_budget: Decimal,
    preferred_price: Decimal | None = None,
) -> PricingResult:
    if unit_cost < 0:
        raise AppError("VALIDATION_ERROR", "总成本不能为负数", field="unit_cost")
    if minimum_gross_margin < 0 or minimum_gross_margin >= 1:
        raise AppError("VALIDATION_ERROR", "最低毛利率必须大于等于0且小于1", field="minimum_gross_margin")
    if visitor_budget <= 0:
        raise AppError("BUDGET_INSUFFICIENT", "游客预算必须大于0", field="visitor_budget", retryable=True)

    margin_price = unit_cost / (Decimal("1") - minimum_gross_margin) if unit_cost else Decimal("0")
    minimum_allowed = money(max(room_minimum_price, margin_price))
    if minimum_allowed > visitor_budget:
        raise AppError(
            "BUDGET_INSUFFICIENT",
            "最低允许售价超过游客预算",
            field="visitor_budget",
            retryable=True,
            suggestion="降低组合成本、提高预算或选择其他资源",
            details={"minimumAllowedPrice": str(minimum_allowed), "budget": str(visitor_budget)},
        )

    # preferred_price is a business-policy input selected by the hotel operator,
    # never an Agent-produced financial value. The backend clamps it to all rules.
    anchor = preferred_price if preferred_price is not None else minimum_allowed
    suggested = money(max(minimum_allowed, min(anchor, visitor_budget)))
    if suggested < unit_cost:
        raise AppError("MARGIN_TOO_LOW", "建议售价低于组合成本", field="suggested_price")
    gross_profit = money(suggested - unit_cost)
    gross_margin = (gross_profit / suggested).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP) if suggested else Decimal("0")
    if gross_margin < minimum_gross_margin:
        raise AppError(
            "MARGIN_TOO_LOW",
            "组合毛利率未达到最低要求",
            field="minimum_gross_margin",
            retryable=True,
            suggestion="选择更低结算价资源或提高售价",
        )
    return PricingResult(unit_cost=money(unit_cost), minimum_allowed_price=minimum_allowed, suggested_price=suggested, gross_profit=gross_profit, gross_margin=gross_margin)

