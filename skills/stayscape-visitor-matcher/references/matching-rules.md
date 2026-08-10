# Matching rules

- Filter by positive inventory and active public status first.
- A product is a match only when its date, weather, child-age, and budget constraints pass.
- Interests improve ranking but cannot override hard constraints.
- Schedule descriptions are explanatory; the merchant's confirmed slot is authoritative.
- Negative preferences are hard exclusions when they identify a category (for
  example TEA, CULTURE, CITY_WALK, SPORT); activity level is a ranking signal
  and can exclude clearly incompatible high-intensity outdoor plans.
- Match the interpreted target crowd to the product persona before returning a
  result. Never use an Agent-selected ID that was not supplied in `products`.
