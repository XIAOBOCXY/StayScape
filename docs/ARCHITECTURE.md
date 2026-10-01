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
        余宿成景总控 + product-generator          visitor-matcher + marketing-writer

Feishu ──▶ official OpenClaw Feishu Channel ──▶ stayscape-main
                                      │
                                      ▼
                         StayScape Tool Plugin
                                      │ private token
                                      ▼
                              FastAPI agent-tools
```

网站运行时的四个 Skill 仍由自托管 OpenClaw 加载。另有一个独立的 `stayscape-clawhive-chat` Skill，供其它 Agent/ClawHive 上传使用；它不加入网站 OpenClaw 调用链，而是使用网页端创建的 Agent API Token 访问 `/api/v1/agent-tools/me`、产品查询和受控候选生成 Tool。生成只创建 `PENDING_CONFIRMATION` 候选，不开放发布、库存或价格修改。这让网站运行时与 ClawHive 对话入口共享同一套后端事实，又保持凭据、会话和权限边界分离。

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

飞书直接对话还会加载 `deploy/openclaw/workspace/AGENTS.md`。它只规定可审计的运营顺序：先查询 FastAPI 事实，再创建 `PENDING_CONFIRMATION` 候选；只有经营者明确说“加入草稿”或“确认发布”才调用确认 Tool。它不包含密钥、提示词原文或模型内部推理。

### 余宿成景 Hotel Ops Skill

这是酒店运营任务的总控 Skill。它先调用受限的机会分析 Tool，取得临期客房、近 14 天经营聚合、带来源天气、审核合作资源和带来源公共文旅知识；再把已验证方向交给 Product Generator 创建待确认候选。它不拥有 Shell、数据库或任意 HTTP 权限，也不能自行发布产品。独立 ZIP 内还提供一套不依赖 SaaS 的 Python 示例数据、计算脚本和测试，用于可复现产品演示。

### Visitor Matcher Skill

理解游客自然语言、正向/负向偏好、人数、儿童年龄、预算、天气和时间，从 FastAPI 提供的产品摘要中给出匹配解释、行程表达、有限调整和饮食/过敏提醒。它不能扩大候选产品范围或改变库存、价格、容量和预约状态。

### ClawHive Chat Skill

`stayscape-clawhive-chat` 是外部 Agent 的游客/运营自然语言入口。它只接收 `STAYSCAPE_SERVER_URL` 与 `STAYSCAPE_AGENT_TOKEN`，先验证 `/me`，再查询当前 Token 绑定酒店的在售产品，或者调用受控候选生成并做自然语言解释。它不能传入或切换 `hotel_id`，不能读数据库，不能使用 JWT，不能发布或修改库存价格。

## Session 与请求上下文

一次性生成/推荐不携带历史；多轮会话使用独立会话键：

- 游客：`visitor:{conversation_id}`
- 酒店：`hotel:{hotel_id}:{conversation_id}`
- 飞书：`feishu:{hotel_id}:{conversation_id}`，同时保留官方 Channel 的 peer session

统一 `RequestContext` 字段为 `source_channel`、`actor_role`、`hotel_id`、`user_id`、`conversation_id` 和 `trace_id`。缺少可靠来源、角色、酒店或 sender 时，Agent Tool fail closed。

## 飞书 Tool 边界

只开放八个固定工具：

1. `stayscape_get_hotel_context`：读取房型、服务和合作资源的必要上下文
2. `stayscape_list_available_products`：读取游客安全的在售产品摘要
3. `stayscape_get_operations_insights`：读取近 14 天脱敏经营聚合信号
4. `stayscape_analyze_hotel_opportunity`：余宿成景的事实机会分析，不创建产品
5. `stayscape_search_travel_knowledge`：检索带来源与更新时间的杭州文旅知识
6. `stayscape_create_product_proposal`：创建待人工确认候选，仍由 FastAPI 重新校验
7. `stayscape_confirm_product_proposal`：经营者明确确认后，才加入草稿或发布
8. `stayscape_recheck_product_health`：在经营者明确要求后重新计算受影响产品，可下调、替换或暂停

不开放发布、删除、库存、成本、价格、SQL、shell 或任意 HTTP。浏览器永远不能拿到 Gateway Token 或 Tool Token。

## 部署边界

Docker Compose 的 Demo 部署不启动 Gateway，使用 Mock Agent 完成可重复演示；`live` profile 构建固定版本的官方 `ghcr.io/openclaw/openclaw:2026.6.9-slim`，Gateway 通过 Docker 内网服务名访问，并仅将 18789 绑定到服务器 loopback 供 SSH 隧道使用。Nginx 只代理 Web/API/WebSocket，不代理 `/v1/responses`。
