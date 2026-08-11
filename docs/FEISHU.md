# 飞书入口与 allowlist

飞书是酒店运营/客服的第二入口，使用官方 OpenClaw Feishu Channel；它和 Web/H5 共用同一个 `stayscape-main`，不运行第二套 Agent 或 bridge。游客主要入口仍是 H5。

## 创建应用

1. 在飞书开放平台创建企业自建应用和机器人
2. 记录 App ID、App Secret；凭证只放 ECS `.env`
3. 按当前飞书开放平台页面授予机器人收发消息、读取会话身份所需权限
4. 事件订阅选择 OpenClaw 文档要求的 WebSocket/长连接方式，不在公网另建 webhook
5. 将机器人加入允许使用的群组，完成飞书侧发布/启用

OpenClaw 配置使用 `connectionMode: websocket`，并设置 `dmPolicy: allowlist`、`groupPolicy: allowlist`、`requireMention: true`、`dynamicAgentCreation.enabled: false`。配置由 `scripts/render_openclaw_config.py` 生成，默认关闭飞书，缺少 App ID/Secret 不影响 Web/H5。

## 环境变量

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=server-side-secret
FEISHU_DM_ALLOW_FROM=ou_operator_open_id
FEISHU_GROUP_ALLOW_FROM=oc_allowed_group_id
FEISHU_GROUP_SENDER_ALLOW_FROM=ou_operator_open_id,ou_support_open_id
FEISHU_OPERATOR_OPEN_ID=ou_operator_open_id
FEISHU_ACTOR_ROLE=HOTEL_OPERATOR
FEISHU_REQUIRE_MENTION=true
```

DM 和群组默认都是 allowlist；群聊要求 mention。sender、group 和 hotel 绑定信息必须由部署者填写，不接受任意公众用户控制酒店系统。

## StayScape Tool

同一个 Agent 可以调用三个固定工具：

- `stayscape_get_hotel_context`
- `stayscape_list_available_products`
- `stayscape_create_product_draft`

插件只访问 FastAPI 的 `/api/v1/agent-tools/*`，携带服务端 Tool Token、来源 `FEISHU`、角色、酒店 ID 和 sender ID。FastAPI 再次校验 allowlist 和权限。`HOTEL_SUPPORT` 只能读上下文/在售产品；`HOTEL_OPERATOR` 才能创建 DRAFT。绝不提供发布、删除、改库存、改成本、改价格、SQL、shell 或 arbitrary HTTP。

## 验证流程

酒店经理发送：

```text
明天还有哪些临期亲子房？杭州下雨，预算700左右，帮我做一个适合一家三口的产品。
```

预期链路：`get_hotel_context` → Product Skill → Agent 返回候选；经理确认“创建这个草稿”后，`create_product_draft` → FastAPI 确定性校验 → Hotel Web 出现 DRAFT。

客服发送：

```text
2大1小，孩子6岁，下雨，预算700，不喝茶，有什么推荐？
```

预期链路：`list_available_products` → Visitor Skill；“不喝茶”只过滤含茶体验，不会清空其他合法产品。

## 日志与排障

酒店端 Skill 日志应记录 `Provider=OPENCLAW`、`Entry=FEISHU`、`Agent=stayscape-main`、Skill、trace、validation、fallback 和 duration。排查顺序：

```bash
docker compose --env-file .env --profile live logs -f openclaw
docker compose --env-file .env --profile live logs -f server
openclaw channels status --json
openclaw skills check --agent stayscape-main --json
```

如果没有真实 App Secret、sender open_id、群组 ID 或模型授权，本地只能完成配置和契约测试，Feishu 消息闭环标记为 NOT VERIFIED。

## 官方参考

- [OpenClaw Feishu channel](https://docs.openclaw.ai/channels/feishu)
- [OpenClaw configuration](https://docs.openclaw.ai/gateway/configuration)
