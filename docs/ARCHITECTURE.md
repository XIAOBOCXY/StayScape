# StayScape 架构与边界

## 运行时拓扑

```text
                           ┌──────────────────────────────┐
Visitor H5 ───────────────▶│                              │
Hotel Web ────────────────▶│ FastAPI + PostgreSQL         │
                           │ 业务编排 / 规则 / 真实数据  │
                           └──────────────┬───────────────┘
                                          │ server-side Bearer token
                                          ▼
                           ┌──────────────────────────────┐
                           │ one OpenClaw Gateway          │
                           │ one Agent: stayscape-main     │
                           │ POST /v1/responses            │
                           └──────────────┬───────────────┘
                                          │ installed Skills
                         ┌────────────────┴────────────────┐
                         ▼                                 ▼
             product-generator                    visitor-matcher

Feishu ──▶ official OpenClaw Feishu Channel ──▶ stayscape-main
                                      │
                                      ▼
                         StayScape Tool Plugin
                                      │ private token
                                      ▼
                              FastAPI agent-tools
```

ClawHive 不在运行时调用链中。两个 Skill 仍然打包为独立 ZIP 上传 ClawHive，用于 Skill 发布、验证、管理和比赛生态展示。

## 职责边界

### FastAPI、PostgreSQL 和确定性规则

- 查询并校验真实房型、服务、合作资源、商户和产品
- 校验资源 allowlist、状态、日期、天气、场次、年龄和最大入住人数
- 使用 Decimal 计算库存、成本、最低售价、建议售价、毛利和毛利率
- 处理事务、锁、预约占用/释放、动态重算和状态更新
- 重新验证 Agent 返回的每个 ID 和业务字段
- 记录 `trace_id`、来源入口、角色、Agent、Skill、Schema、重试和 fallback

### Product Generator Skill

理解酒店经营目标和游客画像，从 FastAPI 提供的合法资源上下文中提出主题、资源选择、产品名称、营销标题、故事、推荐理由、视觉 brief 和替代建议。它不能决定库存、价格、成本、毛利、日期约束或数据库状态。

### Visitor Matcher Skill

理解游客自然语言、正向/负向偏好、人数、儿童年龄、预算、天气和时间，从 FastAPI 提供的产品摘要中给出匹配解释、行程表达、有限调整和饮食/过敏提醒。它不能扩大候选产品范围或改变库存、价格、容量和预约状态。

## Session 与请求上下文

一次性生成/推荐不携带历史；多轮会话使用独立会话键：

- 游客：`visitor:{conversation_id}`
- 酒店：`hotel:{hotel_id}:{conversation_id}`
- 飞书：`feishu:{hotel_id}:{conversation_id}`，同时保留官方 Channel 的 peer session

统一 `RequestContext` 字段为 `source_channel`、`actor_role`、`hotel_id`、`user_id`、`conversation_id` 和 `trace_id`。缺少可靠来源、角色、酒店或 sender 时，Agent Tool fail closed。

## 飞书 Tool 边界

只开放三个固定工具：

1. `stayscape_get_hotel_context`：读取房型、服务和合作资源的必要上下文
2. `stayscape_list_available_products`：读取游客安全的在售产品摘要
3. `stayscape_create_product_draft`：创建 DRAFT，仍由 FastAPI 重新校验

不开放发布、删除、库存、成本、价格、SQL、shell 或任意 HTTP。浏览器永远不能拿到 Gateway Token 或 Tool Token。

## 部署边界

Docker Compose 的 `demo` profile 不启动 Gateway，使用 Mock Agent 完成可重复演示；`live` profile 构建固定版本的官方 `ghcr.io/openclaw/openclaw:2026.6.6`，Gateway 只在 Docker 内网监听 18789。Nginx 只代理 Web/API/WebSocket，不代理 `/v1/responses`。
