# Validation and retry contract

The deterministic backend is the publish gate. Stable failure handling:

- CAPACITY_INSUFFICIENT: select an allowed alternative or reduce the listing
  ceiling in the backend.
- MARGIN_TOO_LOW: use an allowed lower-cost non-core option or the backend
  price floor; never hide the margin problem.
- TIME_CONFLICT: use a supplied non-overlapping session.
- WEATHER_NOT_SUPPORTED: use a weather-compatible supplied resource.
- AGE_NOT_ALLOWED and CROWD_NOT_SUPPORTED: remove the incompatible resource.
- AGENT_RESOURCE_ID_INVALID and FORMAT_ERROR: repair JSON using only the
  supplied allowlist.
- MISSING_REQUIRED_DATA: stop and request the missing operational fact.

No failure may be solved by inventing a resource, a price, or a source fact.
