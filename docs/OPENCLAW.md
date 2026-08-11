# OpenClaw Runtime 配置

StayScape 只维护一个 self-hosted OpenClaw Gateway 和一个 Agent：`stayscape-main`。正式 Web 调用使用 OpenResponses normal Agent Run：`POST /v1/responses`。FastAPI 持有 Gateway Token，浏览器永远不接触 Token。

## 配置收口

```env
MODE=live
AGENT_PROVIDER=openclaw
OPENCLAW_BASE_URL=http://openclaw:18789
OPENCLAW_GATEWAY_TOKEN=<server-side-token>
OPENCLAW_AGENT_ID=stayscape-main
OPENCLAW_MODEL=openclaw/default
OPENCLAW_RESPONSES_PATH=/v1/responses
OPENCLAW_TRANSPORT=responses
```

不再使用 `CLAWHIVE_*`、`OPENCLAW_API_KEY`、`OPENCLAW_INVOKE_PATH`、`OPENCLAW_TOOL_NAME`、`OPENCLAW_LEGACY_FALLBACK` 或共享 `main` session。

## 官方能力的使用方式

- Gateway Responses endpoint 必须显式启用
- 请求使用 Bearer Gateway Token、`x-openclaw-agent-id: stayscape-main`
- 一次性 Product/Visitor 请求不使用会话历史
- 游客多轮使用 `visitor:{conversation_id}`，酒店多轮使用 `hotel:{hotel_id}:{conversation_id}`，飞书使用 channel peer session
- 请求体只使用官方 OpenResponses 字段，不发送未确认的 `text.format=json_object`
- Agent 输出只提供语义和 JSON；FastAPI 重新校验库存、容量、价格、毛利、天气、日期、年龄、状态和预约

## 两个 Skill

Skill 放在 Agent workspace：

```text
~/.openclaw/workspace/skills/stayscape-product-generator/SKILL.md
~/.openclaw/workspace/skills/stayscape-visitor-matcher/SKILL.md
```

部署脚本随后执行：

```bash
openclaw skills list --agent stayscape-main --json
openclaw skills check --agent stayscape-main --json
```

缺少任意一个 Skill 时，Live 部署不会把 `OPENCLAW_SKILLS_READY` 标为 true；FastAPI 也不会伪装成 OpenClaw LIVE。

## Tool policy

OpenClaw 使用 `tools.profile: minimal`，只 allow 三个 StayScape Tool，并 deny runtime、filesystem、UI、nodes、agents 和 automation 工具组。Tool Plugin 通过固定包路径加载，服务端再用 `STAYSCAPE_AGENT_TOOL_TOKEN`、Feishu sender allowlist、hotel_id 和 actor_role 做第二层校验。

## 本地契约调试

没有 OpenClaw 或模型凭证时使用：

```bash
bash scripts/deploy.sh demo
```

这会使用 deterministic Mock Agent；日志必须显示 `MOCK`，fallback 必须明确显示，不得冒充 OpenClaw。真实 Responses、Skill discovery、模型和 Feishu 需要在云端 Live 环境验证。

## 官方参考

- [OpenResponses HTTP API](https://docs.openclaw.ai/gateway/openresponses-http-api)
- [Docker](https://docs.openclaw.ai/install/docker)
- [Configuration](https://docs.openclaw.ai/gateway/configuration)
- [Skills CLI](https://docs.openclaw.ai/cli/skills)
- [Tool plugins](https://docs.openclaw.ai/plugins/tool-plugins)
