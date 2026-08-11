import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";

const configSchema = Type.Object({
  baseUrl: Type.String({ description: "Internal StayScape API URL; never expose it to the visitor." }),
  token: Type.String({ description: "Server-side StayScape Agent Tool token." }),
  hotelId: Type.Integer({ minimum: 1, description: "Hotel bound to this Feishu operator account." }),
  senderId: Type.String({ description: "Feishu sender open_id approved by the StayScape allowlist." }),
  actorRole: Type.Union([Type.Literal("HOTEL_OPERATOR"), Type.Literal("HOTEL_SUPPORT")]),
});

const emptyParameters = Type.Object({}, { additionalProperties: false });

const requestSchema = Type.Object({
  target_date: Type.Optional(Type.String()),
  weather: Type.Optional(Type.String()),
  target_crowd: Type.Optional(Type.String()),
  theme: Type.Optional(Type.String()),
  minimum_gross_margin: Type.Optional(Type.String()),
  visitor_budget: Type.Optional(Type.String()),
  preferred_price: Type.Optional(Type.String()),
  room_inventory_id: Type.Optional(Type.Integer({ minimum: 1 })),
  variant_count: Type.Optional(Type.Integer({ minimum: 1, maximum: 5 })),
  creative_direction: Type.Optional(Type.String()),
  resource_selections: Type.Optional(Type.Array(Type.Object({
    resource_type: Type.Union([Type.Literal("HOTEL_SERVICE"), Type.Literal("PARTNER_RESOURCE")]),
    resource_id: Type.Integer({ minimum: 1 }),
    quantity_per_package: Type.Integer({ minimum: 1, maximum: 100 }),
  }, { additionalProperties: false }))),
}, { additionalProperties: false });

async function callApi(path: string, body: Record<string, unknown>, config: Record<string, unknown>, signal?: AbortSignal) {
  signal?.throwIfAborted();
  const baseUrl = String(config.baseUrl ?? "").replace(/\/$/, "");
  if (!/^https?:\/\//.test(baseUrl)) throw new Error("StayScape baseUrl must be an HTTP(S) URL");
  const response = await fetch(`${baseUrl}/api/v1/agent-tools/${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${String(config.token ?? "")}`,
      "X-StayScape-Source-Channel": "FEISHU",
      "X-StayScape-Actor-Role": String(config.actorRole ?? ""),
      "X-StayScape-Hotel-Id": String(config.hotelId ?? ""),
      "X-StayScape-Sender-Id": String(config.senderId ?? ""),
    },
    body: JSON.stringify(body),
    signal,
  });
  const data = await response.json().catch(() => ({ message: response.statusText }));
  if (!response.ok) throw new Error(`StayScape Tool ${path} failed (${response.status}): ${JSON.stringify(data)}`);
  return data;
}

export default defineToolPlugin({
  id: "stayscape-openclaw-plugin",
  name: "StayScape Business Tools",
  description: "Allowlisted hotel context, public product lookup and validated product drafts for StayScape Feishu operators.",
  configSchema,
  tools: (tool) => [
    tool({
      name: "stayscape_get_hotel_context",
      label: "StayScape Hotel Context",
      description: "Read the bound hotel's safe rooms, services and partner resources for product planning.",
      parameters: emptyParameters,
      outputSchema: Type.Object({ hotel_id: Type.Integer(), rooms: Type.Array(Type.Unknown()), services: Type.Array(Type.Unknown()), partner_resources: Type.Array(Type.Unknown()) }, { additionalProperties: true }),
      optional: true,
      async execute(_params, config, context) {
        return callApi("hotel-context", { hotel_id: Number(config.hotelId), payload: {} }, config, context.signal);
      },
    }),
    tool({
      name: "stayscape_list_available_products",
      label: "StayScape Available Products",
      description: "List current public products using visitor-safe price, theme, schedule and resource facts.",
      parameters: Type.Object({ target_date: Type.Optional(Type.String()), budget: Type.Optional(Type.String()) }, { additionalProperties: false }),
      outputSchema: Type.Object({ items: Type.Array(Type.Unknown()) }, { additionalProperties: true }),
      optional: true,
      async execute(params, config, context) {
        return callApi("available-products", { hotel_id: Number(config.hotelId), payload: params }, config, context.signal);
      },
    }),
    tool({
      name: "stayscape_create_product_draft",
      label: "StayScape Product Draft",
      description: "Create a DRAFT only after FastAPI validates resources, capacity, date, weather and margin.",
      parameters: requestSchema,
      outputSchema: Type.Object({ product_id: Type.Integer(), product: Type.Unknown(), products: Type.Array(Type.Unknown()), trace_ids: Type.Array(Type.String()) }, { additionalProperties: true }),
      optional: true,
      async execute(params, config, context) {
        if (String(config.actorRole) !== "HOTEL_OPERATOR") throw new Error("Only HOTEL_OPERATOR may create product drafts");
        return callApi("product-draft", { hotel_id: Number(config.hotelId), payload: params }, config, context.signal);
      },
    }),
  ],
});
