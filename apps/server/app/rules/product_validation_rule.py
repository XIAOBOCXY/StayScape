from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..core.exceptions import AppError
from .capacity_rule import CapacityInput, CapacityResult, calculate_sale_quantity
from .pricing_rule import PricingResult, calculate_pricing


@dataclass(frozen=True)
class PackageValidation:
    capacity: CapacityResult
    pricing: PricingResult
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": True,
            "errors": [],
            "warnings": self.warnings,
            "saleQuantity": self.capacity.sale_quantity,
            "bottleneckResource": self.capacity.bottleneck_resource,
            "supportedQuantities": self.capacity.supported_quantities,
            "financials": {
                "unitCost": str(self.pricing.unit_cost),
                "minimumAllowedPrice": str(self.pricing.minimum_allowed_price),
                "suggestedPrice": str(self.pricing.suggested_price),
                "grossProfit": str(self.pricing.gross_profit),
                "grossMargin": float(self.pricing.gross_margin),
            },
        }


def validate_package(
    *,
    capacity_inputs: list[CapacityInput],
    unit_cost: Decimal,
    room_minimum_price: Decimal,
    minimum_gross_margin: Decimal,
    visitor_budget: Decimal,
    preferred_price: Decimal | None,
    warnings: list[str] | None = None,
) -> PackageValidation:
    capacity = calculate_sale_quantity(capacity_inputs)
    pricing = calculate_pricing(
        unit_cost=unit_cost,
        room_minimum_price=room_minimum_price,
        minimum_gross_margin=minimum_gross_margin,
        visitor_budget=visitor_budget,
        preferred_price=preferred_price,
    )
    return PackageValidation(capacity=capacity, pricing=pricing, warnings=warnings or [])

