# ClawHive 接入说明

StayScape 的正式 Skill 平台是网易帝王蟹（ClawHive）。两个 ZIP 包可以直接在 ClawHive 的 Skill 页面上传并安装到目标龙虾实例：

- `dist/stayscape-product-generator.zip`
- `dist/stayscape-visitor-matcher.zip`

ClawHive 是 Skill 与龙虾实例的管理平台，实际执行任务的是安装了 Skill 的龙虾 Agent。StayScape 后端不会让浏览器持有平台凭证；如果需要让酒店端直接触发龙虾，必须由用户在 ClawHive/龙虾侧提供一个受保护的 Agent bridge 地址，然后只在后端环境变量配置连接信息。

## 直接调用配置

```env
AGENT_PROVIDER=clawhive
CLAWHIVE_BASE_URL=https://your-clawhive-agent-bridge
CLAWHIVE_GATEWAY_TOKEN=server-side-only
CLAWHIVE_MODEL=your-configured-model
CLAWHIVE_TRANSPORT=responses
CLAWHIVE_RESPONSES_PATH=/v1/responses
CLAWHIVE_AGENT_ID=your-agent-id
CLAWHIVE_SKILL_VERSION=1.0.0
```

`responses` 请求会在任务消息中明确要求使用已安装的 `stayscape-product-generator` 或 `stayscape-visitor-matcher`，并携带现有结构化 JSON。服务端规则引擎仍然负责库存、容量、成本、价格、毛利和状态，Skill 不得成为这些数字的来源。

代码仍兼容旧的 `AGENT_PROVIDER=openclaw` 与 `OPENCLAW_*` 变量，便于迁移已有本地 Agent bridge；这不改变 ClawHive 作为 Skill 上传和安装平台的定位。

如果 ClawHive 当前没有可供第三方服务调用的 HTTP bridge，可以直接在阿里云 Linux ECS 安装官方 OpenClaw Gateway：把两个 Skill 安装到云端 OpenClaw workspace，StayScape FastAPI 通过同机私网地址调用 `/v1/responses`，Windows Hub 通过 SSH 隧道作为可选桌面客户端连接。公网访客只访问 StayScape 网站，不需要安装 ClawHive 或 OpenClaw。完整步骤见 [docs/DEPLOY_ALIYUN.md](DEPLOY_ALIYUN.md)。

## 云端实例的字段对应

云端实例页面中的字段不要混用：

| ClawHive 页面字段 | StayScape 用途 |
|---|---|
| 实例 ID（例如 `5075`） | 运维识别，不作为 HTTP Agent 路由 ID |
| Provider 实例 ID / VM ID | 云厂商资源标识，不是 API 地址 |
| Agent ID（例如 `45826`） | 写入 `CLAWHIVE_AGENT_ID`，通过 `x-openclaw-agent-id` 路由 |
| 私网 IP（例如 `10.0.3.51`） | 只有 StayScape 与云实例处于同一网络时才能作为地址 |

OpenClaw Gateway 通常使用 `18789` 端口，Responses API 还需要在云端配置中开启 `gateway.http.endpoints.responses.enabled`。如果 StayScape 在本地电脑运行，不能直接使用 `10.0.3.51`；应在 ClawHive 云实例页面开通端口映射/公网网关地址，或把 StayScape 后端部署到同一云实例/私网中。`CLAWHIVE_BASE_URL` 只填写协议、主机和端口，例如 `http://127.0.0.1:18789`，不要把 `/v1/responses` 拼进去。

## 验证方式

1. 在 ClawHive 安装两个 Skill，并在龙虾对话中分别验证两个 Skill 的触发方式。
2. 启动 StayScape 后，酒店端「Skill 调用日志」中的 Provider 应显示 `CLAWHIVE`，同时显示 Skill、agent_id、trace_id 和 `fallback=false`。
3. 若没有可供后端调用的 Agent bridge，保持 `AGENT_PROVIDER=mock` 完成本地演示；页面会明确显示 `MOCK` / `Mock Fallback`，不会伪装成 ClawHive 实时调用。

官方入口：[ClawHive](https://skills.netease.im/) · [快速开始](https://skills.netease.im/docs/UserManual/quick-start) · [Skill 使用手册](https://skills.netease.im/docs/BestPractices/skill-user-manual)
