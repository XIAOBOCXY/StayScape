# Deterministic business rules

1. The package contains one room plus at least one hotel service or approved
   partner resource.
2. Formal capacity is the minimum floor(remaining / per_package_quantity)
   across rooms, hotel services, and approved partner resources.
3. Minimum legal price is max(room_min_sell_price,
   total_cost / (1 - minimum_margin_rate)).
4. Margin rate is (sell_price - total_cost) / sell_price. All money is
   calculated with Decimal, not floating point.
5. Only approved=true, status=AVAILABLE, dated, priced, capacity-positive
   partner resources are eligible.
6. A public knowledge entry is never formal inventory and never participates
   in capacity, cost, margin, or availability calculations.
7. A resource replacement must pass the entire capacity, finance, and
   validation sequence again.
8. Demonstration data is explicitly synthetic. It must not be presented as
   real hotel revenue, partner rights, addresses, inventory, or rates.
