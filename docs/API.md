# API 摘要

所有管理端接口前缀为 `/api/v1`，管理端使用 Bearer JWT；游客接口无需登录。

| 场景 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 认证 | POST | `/auth/login` | 酒店/商户登录 |
| 认证 | GET | `/auth/me` | 当前用户 |
| 演示 | POST | `/demo/reset` | 开发环境重置演示数据 |
| 酒店 | GET | `/hotel/dashboard` | 经营总览 |
| 酒店 | GET/PATCH | `/hotel/rooms`、`/hotel/rooms/{id}` | 房量维护 |
| 酒店 | GET/PATCH | `/hotel/services`、`/hotel/services/{id}` | 酒店服务维护 |
| 酒店 | GET/PATCH | `/hotel/resources`、`/hotel/resources/{id}/package` | 资源池和组包许可 |
| 酒店 | POST | `/hotel/products/generate` | Agent候选+规则校验生成 |
| 酒店 | PATCH | `/hotel/products/{id}/status` | 模拟发布、暂停、下架 |
| 商户 | GET/PATCH | `/merchant/resources`、`/merchant/resources/{id}` | 商户名额、价格、状态 |
| 游客 | GET | `/visitor/products` | 可售产品 |
| 游客 | POST | `/visitor/consult` | 智能咨询 |
| 游客 | POST | `/visitor/recommend` | 个性化推荐 |
| 游客 | POST | `/visitor/intents` | 预约意向 |
| 实时 | WS | `/ws/hotel/{hotel_id}` | 资源变化通知 |

## 统一错误结构

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

