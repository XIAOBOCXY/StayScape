# Fallback and freshness rules

- Live tool error: do not claim completion. Explain which Tool failed and ask
  the operator to retry or maintain the missing fact.
- Missing room/service/resource data: return MISSING_REQUIRED_DATA and stop
  before marketing generation.
- Weather verification is stale or unavailable: retain the prior compatible
  plan only as 信息需确认; do not assert a weather fact or auto-publish.
- A public knowledge record that is VERIFY_REQUIRED or STALE can inspire a
  route option only when it carries its source and an explicit confirmation
  note. It never becomes an included entitlement.
- A failed validator cannot be hidden by rewriting copy. Repair the inputs,
  then calculate and validate again.
