# StayScape API 摘要

所有接口前缀为 `/api/v1`。酒店端和商户端使用 FastAPI JWT；游客接口无需登录。浏览器只调用 StayScape API，不直接访问 OpenClaw Gateway。

## 主要接口

| 场景 | 方法 | 路径 | 用途 |
|---|---|---|---|
| 认证 | POST | `/auth/login` | 酒店/商户登录 |
| 经营总览 | GET | `/hotel/dashboard` | 房间、资源、产品和预约统计 |
| 临期客房 | GET/POST/PATCH | `/hotel/rooms`、`/hotel/rooms/{id}` | 维护房型、日期、库存、价格和入住人数 |
| 酒店服务 | GET/PATCH | `/hotel/services`、`/hotel/services/{id}` | 维护早餐、延迟退房及其他服务 |
| 合作资源 | GET/PATCH | `/hotel/resources`、`/hotel/resources/{id}/package` | 查看资源、切换组包许可 |
| 产品生成 | POST | `/hotel/products/generate` | 调用 Product Skill，按产品类型、人数套餐与真实库存生成候选；随后由规则引擎计算库存和价格 |
| 候选批量改稿 | POST | `/hotel/products/refine-marketing` | 经营者用一句自然语言同时调整多套候选的文案、SVG 海报与可选 AI 配图；不触碰库存、价格或发布状态 |
| AI 运营任务 | POST/GET | `/hotel/ai/conversations`、`/hotel/ai/conversations/{id}/messages` | Web 与飞书共用的自然语言酒店运营任务；生成待确认候选 |
| AI 候选确认 | GET/POST | `/hotel/ai/proposals`、`/hotel/ai/proposals/{id}/confirm` | 明确加入草稿或发布；发布前再次校验实时库存 |
| AI 事实面板 | GET | `/hotel/ai/overview` | 聚合经营信号、天气、文旅知识和待确认数量；不返回内部推理 |
| 产品维护 | GET/PATCH/DELETE | `/hotel/products/{id}` | 查看、编辑、删除产品 |
| 营销素材 | POST | `/hotel/products/{id}/marketing-assets` | 生成或刷新海报、社媒文案、短视频脚本和门店卖点 |
| 产品状态 | PATCH | `/hotel/products/{id}/status` | 模拟发布、暂停和下架 |
| 动态运营 | GET | `/hotel/dynamic-operations` | 查看资源变化和产品重算结果 |
| 商户资源 | GET/POST/PATCH | `/merchant/resources`、`/merchant/resources/{id}` | 维护名称、日期、场次、名额、状态和组包信息 |
| 游客产品 | GET | `/visitor/products` | 浏览当前可售产品 |
| 需求解析 | POST | `/visitor/interpret` | 自然语言解析为可编辑需求卡 |
| 游客推荐 | POST | `/visitor/recommend` | 使用确认后的结构化需求进行确定性筛选和 Visitor Skill 解释 |
| 智能咨询 | POST | `/visitor/consult` | 多轮游客咨询和产品安全摘要问答 |
| 预约意向 | POST | `/visitor/intents` | 提交含人数、预算、时间和过敏信息的预约意向 |
| 实时通知 | WS | `/ws/hotel/{hotel_id}` | 酒店端实时接收动态重算事件 |

## Feishu Tool 内部接口

以下接口只接受 OpenClaw Tool Plugin 的服务端 Bearer Token，并要求 `FEISHU`、酒店角色、酒店 ID 和 allowlist sender 上下文。它们不对浏览器开放：

| 方法 | 路径 | 权限 | 用途 |
|---|---|---|---|
| POST | `/agent-tools/hotel-context` | HOTEL_OPERATOR/HOTEL_SUPPORT | 返回房间、服务和合作资源的运营字段 |
| POST | `/agent-tools/available-products` | HOTEL_OPERATOR/HOTEL_SUPPORT | 返回游客安全的当前产品摘要 |
| POST | `/agent-tools/operations-insights` | HOTEL_OPERATOR/HOTEL_SUPPORT | 返回隐私安全的近 14 天经营聚合和实时机会信号 |
| POST | `/agent-tools/travel-knowledge` | HOTEL_OPERATOR/HOTEL_SUPPORT | 返回带来源和核验状态的杭州文旅知识；不等于可售资源 |
| POST | `/agent-tools/product-proposal` | HOTEL_OPERATOR | 创建 `PENDING_CONFIRMATION` 产品候选，资源、库存、容量、时间和利润仍由 FastAPI 校验 |
| POST | `/agent-tools/proposal-confirm` | HOTEL_OPERATOR | 仅在飞书明确确认后加入草稿或发布；发布时重新复核实时库存 |

Tool 不提供删除、改库存、改成本、改价格、SQL、Shell 或任意 HTTP 能力；唯一的发布入口是允许名单经营者对某个已校验候选进行显式确认。

## 错误结构

```json
{
  "success": false,
  "error": {
    "code": "PARTNER_CAPACITY_INSUFFICIENT",
    "message": "合作体验名额不足",
    "field": "remainingCapacity",
    "retryable": true,
    "suggestion": "降低套餐库存或选择其他可用体验"
  }
}
```

## 业务边界

Agent 只能提出主题、资源候选、推荐理由和营销内容。库存、成本、售价、毛利、日期、天气、年龄、资源状态、预约占用和数据库写入始终由 FastAPI、PostgreSQL 和确定性规则负责。
