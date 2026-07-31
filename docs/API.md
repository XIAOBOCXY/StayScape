# API 摘要

所有管理端接口前缀为 `/api/v1`，管理端使用 Bearer JWT；游客接口无需登录。

| 场景 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 认证 | POST | `/auth/login` | 酒店/商户登录 |
| 认证 | GET | `/auth/me` | 当前用户 |
| 演示 | POST | `/demo/reset` | 开发环境重置演示数据 |
| 酒店 | GET | `/hotel/dashboard` | 经营总览 |
| 酒店 | GET/POST/PATCH | `/hotel/rooms`、`/hotel/rooms/{id}` | 临期客房新增与维护，支持房型、入住日期、库存、价格、入住人数和备注 |
| 酒店 | GET/PATCH | `/hotel/services`、`/hotel/services/{id}` | 酒店服务维护 |
| 酒店 | GET/PATCH | `/hotel/resources`、`/hotel/resources/{id}/package` | 资源池和组包许可；切换时提交 `{"package_enabled": true/false}` |
| 酒店 | POST | `/hotel/products/generate` | Agent候选+规则校验生成，可通过 `variant_count` 生成多套候选 |
| 酒店 | GET/PATCH/DELETE | `/hotel/products/{id}` | 产品详情、内容/天气/入住日期编辑、删除 |
| 酒店 | POST | `/hotel/products/{id}/marketing-assets` | 重新生成图文海报、社媒文案、短视频脚本和门店卖点卡 |
| 酒店 | PATCH | `/hotel/products/{id}/status` | 模拟发布、暂停、下架 |
| 商户 | GET/POST/PATCH | `/merchant/resources`、`/merchant/resources/{id}` | 资源名称、日期、起止场次、名额、价格、天气和状态 |
| 游客 | GET | `/visitor/products` | 可售产品 |
| 游客 | POST | `/visitor/consult` | 智能咨询 |
| 游客 | POST | `/visitor/interpret` | 将同行人数、目的地、预算、兴趣和注意事项整理为可确认的需求卡 |
| 游客 | POST | `/visitor/recommend` | 用户确认需求卡后，按真实库存、天气、时间、容量和毛利条件进行个性化推荐 |
| 游客 | POST | `/visitor/intents` | 接收自然语言预约意向，并由后端确定性解析儿童、饮食和过敏风险 |
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
