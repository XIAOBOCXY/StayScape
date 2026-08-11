# StayScape 测试报告基线

以下是本次增量升级在本地环境实际执行的结果；云端 OpenClaw、模型供应商和飞书需要凭证后再做 Live 联调。

## 已实际验证

```text
Backend pytest: 43 passed, 2 warnings
Frontend npm run build: passed
Skill packaging: passed; two ZIP files generated
OpenClaw plugin TypeScript build: passed
```

后端覆盖：

- 亲子房 6、早餐 30、延迟退房 6、非遗名额 12 生成 4 套；12 → 4 后变为 1 套 LOW_STOCK。
- 资源状态、组包许可、天气、日期、容量、年龄和共享库存校验。
- 多候选差异化生成、产品命名、营销素材和 SVG 长文本换行。
- 游客自然语言解释、结构化确认优先级、预约人数、过敏字段和预约库存占用。
- OpenResponses 请求、Bearer 鉴权、`stayscape-main` 路由、隔离 session、超时重试、JSON 修复和 Mock fallback。
- 负向偏好只过滤不兼容产品；“不喝茶”仍可返回不含茶的产品。
- Feishu Tool Token、sender allowlist、角色隔离、游客不能创建草稿，以及游客安全产品上下文。

## 云端部署后应执行

```bash
docker compose --env-file .env --profile live config
docker compose --env-file .env --profile live ps
docker compose --env-file .env --profile live exec openclaw openclaw skills list --agent stayscape-main --json
docker compose --env-file .env --profile live exec openclaw openclaw skills check --agent stayscape-main --json
curl -fsS http://127.0.0.1/health
```

如果模型 API/OAuth 尚未配置，Gateway 和 Skill discovery 可以通过，但实际生成/推荐会标记为未完成；不得把它报告成 OpenClaw LIVE 成功。

## 未验证项

- `NOT VERIFIED`：阿里云公网 HTTPS、域名和证书，原因是需要域名解析和证书配置。
- `NOT VERIFIED`：真实 OpenClaw 模型生成，原因是尚未提供模型 API Key/OAuth。
- `NOT VERIFIED`：真实飞书消息往返，原因是尚未提供 App ID、App Secret、allowlist 用户和事件配置。
- `NOT VERIFIED`：第三方景区/商户实时库存，项目只使用演示合作资源和允许的素材来源。
