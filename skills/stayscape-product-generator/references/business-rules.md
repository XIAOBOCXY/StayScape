# Business rules

1. A formal package must contain a room and at least one hotel service or partner resource.
2. A partner resource is selectable only when its merchant is ACTIVE, package_enabled is true, status is AVAILABLE, and remaining capacity is positive.
3. Weather, date, crowd, child age, and time constraints are checked by the backend.
4. The backend calculates sale quantity as the minimum floor(capacity / per-package consumption) across finite resources.
5. The backend calculates cost, minimum allowed price, selling price, gross profit, and gross margin with Decimal.

