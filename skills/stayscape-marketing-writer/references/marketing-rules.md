# Marketing writing rules

- The backend is the source of truth. Never compute or claim inventory, cost,
  price, gross profit, or gross margin. Copy may reference the supplied price
  and remaining capacity only as given.
- Reference only resource names, times and addresses present in the input.
  Never invent a landmark, attraction, brand, endorsement or right.
- `PUBLIC_REFERENCE` resources are recommendation-only and must never be
  written as a bookable package element.
- Do not create poster artwork, SVG, or image-generation prompts. Keep existing product photos attached to their source resources.
- Honor the supplied `creative_direction` marketing style when present.
- Preserve allergy, child-age, weather and time-conflict risk in the copy.
  Never promise that an experience is safe or available; route those to hotel
  and merchant confirmation.
- Do not return `recommendation_reason` or `risk_message`; those are product
  fields owned by the product generator.
