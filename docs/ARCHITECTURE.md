# 架构与边界

```text
游客 H5 / 酒店经营端 / 商户端
              │ Axios + WebSocket
              ▼
        FastAPI API 层
              │
     Service / Repository 层
       ┌──────┴────────┐
       │               │
  确定性规则引擎      Agent 适配层
  capacity/pricing    Mock/ClawHive Agent bridge
  availability/time   JSON Schema + trace_id
  weather/crowd       fallback
       │               │
       └──────┬────────┘
              ▼
       SQLAlchemy 2.x
       SQLite / PostgreSQL
```

## AI 与程序分工

Agent 只能输出主题、资源候选、自然语言理由、文案和推荐解释。后端重新从数据库读取资源，校验 allowlist、日期、天气、时间、客群、年龄、商户状态和组包许可，并用 Decimal 计算容量、成本、最低售价、建议售价、毛利和状态。

## 事务一致性

酒店或商户更新资源时，资源更新、ResourceChangeEvent、受影响 TravelProduct 重算和 ProductAdjustmentRecord 在同一 SQLAlchemy Session 事务中提交；关键查询使用 `with_for_update()`，PostgreSQL 下可获得行级锁。WebSocket 在事务提交后发送通知。

## 资源与套餐关系

`product_resources` 保存组包时的资源快照和每套消耗量，但重算时永远按 `resource_id` 读取实时资源。这样可以保留产品历史组成，同时保证容量和状态跟随商户实时变化。
