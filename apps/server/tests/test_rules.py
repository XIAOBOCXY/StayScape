from decimal import Decimal

import pytest

from app.core.exceptions import AppError
from app.rules.capacity_rule import CapacityInput, calculate_sale_quantity
from app.rules.pricing_rule import calculate_pricing


def test_demo_capacity_is_four_and_bottleneck_is_experience():
    result = calculate_sale_quantity([
        CapacityInput("亲子房", 6, 1),
        CapacityInput("家庭早餐", 30, 3),
        CapacityInput("延迟退房", 6, 1),
        CapacityInput("室内非遗手作体验", 12, 3),
    ])
    assert result.sale_quantity == 4
    assert result.bottleneck_resource == "室内非遗手作体验"


def test_capacity_four_becomes_one():
    result = calculate_sale_quantity([CapacityInput("亲子房", 6, 1), CapacityInput("家庭早餐", 30, 3), CapacityInput("室内非遗手作体验", 4, 3)])
    assert result.sale_quantity == 1


def test_zero_consumption_is_rejected():
    with pytest.raises(AppError) as error:
        calculate_sale_quantity([CapacityInput("资源", 4, 0)])
    assert error.value.code == "VALIDATION_ERROR"


def test_demo_pricing_is_decimal_exact():
    result = calculate_pricing(unit_cost=Decimal("455"), room_minimum_price=Decimal("399"), minimum_gross_margin=Decimal("0.20"), visitor_budget=Decimal("700"), preferred_price=Decimal("599"))
    assert result.unit_cost == Decimal("455.00")
    assert result.suggested_price == Decimal("599.00")
    assert result.gross_profit == Decimal("144.00")
    assert str(result.gross_margin).startswith("0.2404")


def test_budget_error_is_structured():
    with pytest.raises(AppError) as error:
        calculate_pricing(unit_cost=Decimal("600"), room_minimum_price=Decimal("399"), minimum_gross_margin=Decimal("0.20"), visitor_budget=Decimal("700"), preferred_price=Decimal("599"))
    assert error.value.code == "BUDGET_INSUFFICIENT"

