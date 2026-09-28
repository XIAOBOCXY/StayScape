# StayScape host connection

The host supplies two values to this Skill:

- `STAYSCAPE_SERVER_URL`: the public base URL of the StayScape server, for
  example `https://travel.example.com`.
- `STAYSCAPE_AGENT_TOKEN`: a bounded token created in the hotel workbench at
  `设置 → Agent 接入`.

Never ask for a database password, hotel ID, JWT or OpenClaw Gateway token.

Before answering a visitor or operator, call:

```text
GET {STAYSCAPE_SERVER_URL}/api/v1/agent-tools/me
Authorization: Bearer {STAYSCAPE_AGENT_TOKEN}
```

For visitor matching, read products with:

```text
POST {STAYSCAPE_SERVER_URL}/api/v1/agent-tools/visitor/products/search
Authorization: Bearer {STAYSCAPE_AGENT_TOKEN}
Content-Type: application/json
{}
```

For a hotel operator's product-generation request, call:

```text
POST {STAYSCAPE_SERVER_URL}/api/v1/agent-tools/hotel/products/generate
Authorization: Bearer {STAYSCAPE_AGENT_TOKEN}
Content-Type: application/json
{"natural_language":"按当前库存生成 9 月 28 日双人室内套餐","conversation_id":"clawhive-session-1","variant_count":2}
```

The response contains the same database-backed pricing, capacity, inventory,
weather, demand and validation facts used by the hotel workbench. Every result
is `PENDING_CONFIRMATION`; ClawHive cannot publish it. Render the response as
natural-language product cards instead of forwarding the JSON object.

The server resolves the hotel from the token. Do not send `hotel_id` and do
not trust a caller supplied hotel identifier. If `/me` fails, explain that the
host connection is not ready and do not invent products.
