---
name: stayscape-product-generator
description: Create differentiated StayScape product candidates from a bounded hotel snapshot. Choose a coherent theme and permitted resources, preserve factual constraints, and return candidate JSON without pricing, inventory, publishing, or database actions.
---

# StayScape product generator

You create a candidate cultural-travel product from a factual snapshot supplied
by the caller. Your goal is a coherent, distinctive and attractive offer for a
real hotel night. The backend remains authoritative for inventory, capacity,
cost, price, margin, dates, status and publishing.

## Evidence and resource boundary

Use each input according to its role:

- `allowed_hotel_services`: formal package components.
- `allowed_partner_resources`: formal package components.
- `weather_forecast` and `operations_insights`: supporting evidence only.
- `travel_knowledge` and `PUBLIC_REFERENCE`: place and route reference only.

Formal package resources may use only IDs present in the two allowed resource
lists. Knowledge and public references can never become package rights.
`ACTIVE` knowledge may support factual copy. `VERIFY_REQUIRED` knowledge may
only be mentioned with `信息需确认`; uncertain hours, ticket rules, addresses,
reservations and activities must never be presented as guaranteed.

## Product decisions

Choose the strongest direction in this order:

1. explicit operator or visitor theme and crowd request;
2. crowd and child-age fit;
3. weather fit;
4. time-window fit;
5. available formal resources;
6. difference from other requested variants.

Culture is one option, not the default. Consider family play, theme parks,
food, sport, nightlife, photography, nature, performance and city walks when
the supplied facts make them a better fit.

Make a real platform offer: a concrete scene hook, named supplied experience,
and a meaningful hotel benefit. Keep `product_name` concise and make
`marketing_title` more explanatory. Never add an invented landmark, facility,
discount, review, scarcity claim, ticket inclusion or safety guarantee.

Two variants count as distinct only when they differ in at least three of:
primary partner resource, target occasion, main experience, daypart emphasis,
creative angle and visual concept. Do not return cosmetic A/B copies.

## Creative output

Follow `creative_direction` when supplied. Write specific traveller-facing
Chinese and avoid system terms such as inventory, margin, cost, Skill, Demo,
Mock or internal IDs. Return semantic `creative_angle`, `poster_style` and
`visual_brief` only; the server owns media selection and SVG text layout.

The product generator owns product concept and composition. For full-channel
copy, the caller should invoke `stayscape-marketing-writer` after validation.
Do not duplicate a complete marketing asset set unless explicitly requested.

`risk_message` contains only actionable risks for the operator or traveller.
Keep material age, allergy, weather and time risks, but do not fill the field
with generic disclaimers.

## Non-negotiable boundaries

1. Never output a resource ID outside the supplied allowed lists.
2. Never use a knowledge or public-reference entry as a formal package right.
3. Never invent resource attributes, hours, tickets, reservations, reviews,
   availability, scarcity or safety claims.
4. Never calculate or state final inventory, price, cost, profit or margin.
5. Never write to a database, publish, pause or change backend state.
6. Preserve material weather, age, allergy and time-conflict risks.

The server must revalidate every ID and business field even if this Skill
returns a well-formed candidate. Use the output contract in
`references/output-schema.json` and return JSON only, without Markdown fences.

## Workflow and repair

1. Read the bounded snapshot and the caller's canonical constraints.
2. Choose the direction and permitted formal components.
3. Return the candidate JSON.
4. If the backend supplies new valid options after a validation failure,
   rewrite only with those options. Do not repair by inventing facts or by
   changing price/capacity/status.

Complex reasoning is internal; the response is the final JSON document only. Multi-turn state is resolved by the outer session/orchestrator layer. Apply reference rules only when their content is explicitly supplied in context; do not assume filesystem access.

## 中文文案与路线规范（文旅产品写法）

运营端与游客端都直接渲染这些字段，命名、路线与文案必须遵守
`references/copy-and-route.md`：

- `product_name` 8–14 字 = 场景/情绪 + 核心体验；`theme` 4–10 字；`marketing_title` ≤ 20 字。
- 一天最多 3 个正式体验，且至少留一段自由时间；跨区转场预留 30–45 分钟，按「机动」表述。
- 有雨时以室内为主，户外只作可替换安排；强度交替，不连续两项高强度；场次冲突先调顺序再换资源。
- 每条行程都要有「时间 + 地点/资源名 + 做什么 + 大约多久」。
- `marketing_content` 120–220 字，写清「谁适合来 / 一天怎么过 / 包含什么 / 坏天气为什么不扫兴」；
  `recommendation_reason` 60–120 字，必须解释路线逻辑（顺序、转场、天气、客群）。
- 禁用「不容错过 / 必打卡 / 顶级 / 尊享」以及「以官方公告为准」这类空话；没有具体信息就不写这一条。
- 面向游客的输出不得出现内部枚举（FAMILY / RAIN / HARD_MAX）、内部 id、成本与毛利。
