# Natural-language output guidance

The ClawHive Skill intentionally returns prose instead of a machine JSON
object. The host API remains structured; the Skill turns the structured result
into a readable workbench-style card.

For generated candidates, preserve these facts when present:

- product name, theme, date, crowd, party size and room
- formal included resources and time windows
- suggested price, unit cost, minimum legal price, gross profit and margin
- sale quantity and bottleneck resource
- why recommended evidence and validation checks
- pending human confirmation status and material risks

For visitor matching, show only published and currently sellable products,
with fit reasons and trade-offs. Do not expose internal IDs as the main answer.
