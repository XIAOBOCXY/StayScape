# OpenClaw Runtime 配置

StayScape 只维护一个 self-hosted OpenClaw Gateway 和一个 Agent：`stayscape-main`。正式 Web 调用使用 OpenResponses normal Agent Run：`POST /v1/responses`。FastAPI 持有 Gateway Token，浏览器永远不接触 Token。

## 配置收口

```env
MODE=live
AGENT_PROVIDER=openclaw
OPENCLAW_BASE_URL=http://openclaw:18789
OPENCLAW_GATEWAY_TOKEN=<server-side-token>
OPENCLAW_AGENT_ID=stayscape-main
OPENCLAW_AGENT_TARGET=openclaw/default
OPENCLAW_PRIMARY_MODEL=qwen/qwen3.5-plus
QWEN_API_KEY=<server-side-qwen-key>
OPENCLAW_RESPONSES_PATH=/v1/responses
OPENCLAW_TRANSPORT=responses
```

## 哪些值可以配置

服务器地址、端口、密钥、模型、酒店绑定、飞书 allowlist 和部署模式都通过服务器端
`.env` 配置；Vue 浏览器不会拿到 Gateway Token、Qwen Key 或 Tool Token。`/v1/responses`
是当前 OpenClaw 官方 OpenResponses 协议入口，代码只保留这个正式 transport，不能通过
浏览器切换到未经验证的旧版 Skill/Tool invoke 路径。`OPENCLAW_AGENT_TARGET` 和
`OPENCLAW_PRIMARY_MODEL` 可以改，但必须分别表示 Agent 路由目标和 provider/model，不能
混成一个字段。生产部署默认使用 Docker 内网地址 `http://openclaw:18789`；Gateway 的
宿主机映射固定为 `127.0.0.1:18789`，只供 SSH 隧道使用，不对公网开放。

## Qwen 模型配置

StayScape 的 Live 版本统一使用 Qwen provider；`OPENCLAW_AGENT_TARGET` 是
OpenResponses 的 Agent 路由目标，`OPENCLAW_PRIMARY_MODEL` 才是
`stayscape-main` 的默认后端模型。两者不要混写成一个配置项。

在阿里云部署时，到阿里云百炼/Model Studio 开通模型服务并创建 **Standard
按量 API Key**，选择中国区标准 Key（官方 provider 使用
`qwen-standard-api-key-cn`）。模型使用量按云端账户规则计费；不要把 Token Plan
Key 当作无人值守的公网业务后端凭证。将 Key 只写入服务器上的
`/opt/StayScape/.env`：

```env
OPENCLAW_AGENT_TARGET=openclaw/default
OPENCLAW_PRIMARY_MODEL=qwen/qwen3.5-plus
QWEN_API_KEY=在百炼控制台创建的服务端Key
```

`.env` 只由 Docker Compose 注入 OpenClaw 容器，浏览器、Skill ZIP、Dockerfile、
GitHub 和前端代码都不会读取或保存该 Key。首次 Live 部署会执行 provider 列表
检查和一次真实 `/v1/responses` smoke test；没有 Key 时应明确失败，不能显示
`OPENCLAW LIVE` 或静默伪装成 Mock。

本地无模型费用演示使用 `bash scripts/deploy.sh demo`；正式比赛环境使用
`bash scripts/deploy.sh live`。官方 Qwen provider 的安装与认证方式以
[OpenClaw Qwen provider 文档](https://docs.openclaw.ai/providers/qwen) 为准。

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

Live 部署只有在 Gateway 健康、`stayscape-main` 路由、Qwen provider、两个 Skill、StayScape Tool Plugin、模型清单和一次真实 `/v1/responses` smoke test 全部通过后，才会将 `OPENCLAW_SKILLS_READY` 与 `OPENCLAW_LIVE_READY` 标为 true；FastAPI 不会伪装成 OpenClaw LIVE。

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
