from dataclasses import dataclass

from ..core.exceptions import AppError


@dataclass(frozen=True)
class CapacityInput:
    name: str
    available_quantity: int | None
    quantity_per_package: int
    unlimited: bool = False


@dataclass(frozen=True)
class CapacityResult:
    sale_quantity: int
    bottleneck_resource: str | None
    supported_quantities: dict[str, int | None]


def calculate_sale_quantity(resources: list[CapacityInput]) -> CapacityResult:
    if not resources:
        raise AppError("VALIDATION_ERROR", "至少需要一个有容量约束的资源", field="resources")

    supported: dict[str, int | None] = {}
    finite: list[tuple[str, int]] = []
    for resource in resources:
        if resource.quantity_per_package <= 0:
            raise AppError(
                "VALIDATION_ERROR",
                "每套资源消耗量必须大于0",
                field=resource.name,
                suggestion="请将 quantity_per_package 设置为正整数",
            )
        if resource.unlimited or resource.available_quantity is None:
            supported[resource.name] = None
            continue
        if resource.available_quantity < 0:
            raise AppError("VALIDATION_ERROR", "资源库存不能为负数", field=resource.name)
        value = resource.available_quantity // resource.quantity_per_package
        supported[resource.name] = value
        finite.append((resource.name, value))

    if not finite:
        return CapacityResult(sale_quantity=0, bottleneck_resource=None, supported_quantities=supported)

    bottleneck_resource, sale_quantity = min(finite, key=lambda item: item[1])
    return CapacityResult(
        sale_quantity=sale_quantity,
        bottleneck_resource=bottleneck_resource,
        supported_quantities=supported,
    )

