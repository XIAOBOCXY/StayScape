# StayScape 阿里云公网部署与 OpenClaw 云端运行

## 结论

这条路线可行，也是目前没有 ClawHive 第三方 HTTP 接口时最稳妥的比赛部署方式：

```text
游客浏览器
    │ 只访问 80/443
    ▼
阿里云 ECS：Nginx
    ├── Vue 游客 H5 / 酒店端 / 商户端
    └── FastAPI ── PostgreSQL
                    │ 服务端 Token
                    ▼
              OpenClaw Gateway
              仅云服务器内部可访问

Windows Hub ── SSH 隧道 ──► 同一个云端 OpenClaw Gateway（可选的运维客户端）
```

网站访客不需要安装 OpenClaw，也不会看到 OpenClaw Token。Windows Hub 只是管理员查看和操作云端 Agent 的桌面客户端，不是游客访问 StayScape 的必要组件。

本项目已经为这条拓扑预留了：

- `AGENT_PROVIDER=openclaw` 和官方 Responses transport；
- `OPENCLAW_BASE_URL`、`OPENCLAW_GATEWAY_TOKEN`、`OPENCLAW_AGENT_ID`；
- Docker 容器访问同一台 Linux 主机的 `host.docker.internal`；
- Nginx 统一代理 `/api/`、`/ws/` 和 `/health`；
- `scripts/deploy_aliyun.sh` 一键构建和启动 StayScape；
- `scripts/install_openclaw_linux.sh` 官方安装脚本封装；
- PostgreSQL 数据卷、自动迁移、健康检查和可选演示 Seed。

OpenClaw 的 OpenResponses API 默认关闭，开启后使用同一 Gateway 端口的 `/v1/responses`，请求需要 Gateway 鉴权，并可通过 `openclaw/default` 或 `x-openclaw-agent-id` 路由 Agent。[OpenResponses API 官方文档](https://docs.openclaw.ai/gateway/openresponses-http-api)

## 一、购买阿里云 ECS

打开阿里云 ECS 控制台的自定义购买入口：[ECS 自定义购买](https://ecs-buy.aliyun.com/)。比赛演示建议：

- 规格：4 vCPU / 8 GB 内存；
- 系统：Ubuntu 22.04/24.04 LTS x64，或阿里云 Linux 3 x64；
- 磁盘：系统盘 40 GB 起，建议 80 GB SSD；
- 网络：专有网络 VPC，分配公网 IPv4；
- 带宽：演示阶段 3～5 Mbps 通常够用；
- 磁盘快照：部署完成后创建一次快照，方便赛前恢复。

OpenClaw、StayScape、PostgreSQL 同机运行时，4 vCPU/8 GB 比 2 vCPU/4 GB 更适合现场演示。实际价格会随地域、包年包月/按量付费、带宽和优惠变化，应以购买页面和费用明细为准。

### 安全组

建议只放行：

| 端口 | 用途 | 来源 |
|---|---|---|
| 22/TCP | SSH 管理 | 仅你的办公公网 IP；临时调试可短时间放开 |
| 80/TCP | 网站 HTTP | `0.0.0.0/0` |
| 443/TCP | 网站 HTTPS | `0.0.0.0/0` |

不要对公网放行 `18789`、`5432`、`8000`、`8080`。OpenClaw Gateway 和数据库不应该作为公共接口暴露。阿里云文档也建议公网网站只按需开放 80/443，SSH 22 限制为可信来源。[阿里云 ECS 安全组指南](https://help.aliyun.com/zh/ecs/user-guide/start-using-security-groups)

如果使用中国内地地域和正式域名，需要按阿里云 ICP 备案要求处理；阿里云说明内地服务器上的网站域名在正式对外服务前需要完成相应备案流程。[阿里云 ICP 备案快速入门](https://help.aliyun.com/zh/icp-filing/basic-icp-service/getting-started/quick-start-for-icp-filing-for-personal-websites)

## 二、登录服务器并安装基础工具

在本地 Windows PowerShell 中执行，替换为你的 ECS 公网 IP 和 SSH 用户：

```powershell
ssh root@<ECS公网IP>
```

在云服务器内执行：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git unzip openssl
```

安装 Docker Engine 和 Compose v2。可以使用阿里云镜像/云助手提供的 Docker 安装方式，或使用 Docker 官方安装文档。安装完成后验证：

```bash
docker --version
docker compose version
```

如果当前 SSH 用户不是 root，按 Docker 安装提示把用户加入 `docker` 组并重新登录。不要把数据库端口映射到公网。

## 三、下载 StayScape 并配置

```bash
cd /opt
sudo git clone https://github.com/XIAOBOCXY/StayScape.git
sudo chown -R "$USER":"$USER" /opt/StayScape
cd /opt/StayScape
cp .env.example .env
chmod 600 .env
```

编辑 `.env`：

```env
APP_ENV=production
STAYSCAPE_HTTP_PORT=80
SEED_DEMO_ON_STARTUP=true

# 首次部署前请替换为随机长字符串；deploy_aliyun.sh 也会自动生成
SECRET_KEY=请改成随机长字符串
POSTGRES_PASSWORD=请改成随机长字符串

# 先使用 Mock 完成云端 UI 演示也可以；接通 OpenClaw 后改为 openclaw
AGENT_PROVIDER=openclaw
OPENCLAW_BASE_URL=http://host.docker.internal:18789
OPENCLAW_GATEWAY_TOKEN=只放服务端的GatewayToken
OPENCLAW_MODEL=openclaw/default
OPENCLAW_TRANSPORT=responses
OPENCLAW_RESPONSES_PATH=/v1/responses
# 默认 Agent 可留空；如果 openclaw 控制台显示明确 Agent ID，再填写
OPENCLAW_AGENT_ID=
```

`OPENCLAW_BASE_URL` 只填写协议、主机和端口，不要写 `/v1/responses`。 `host.docker.internal` 是 StayScape API 容器访问同一台 ECS 主机上原生 OpenClaw 的地址；本项目 Compose 已加入 Linux Docker 的 host-gateway 映射。

## 四、在云端 Linux 安装 OpenClaw

OpenClaw 官方 Linux 安装页推荐使用安装脚本；Linux Gateway 由 Node 运行，安装后可用 systemd 常驻。[OpenClaw Linux 官方文档](https://docs.openclaw.ai/linux)

在 `/opt/StayScape` 目录执行：

```bash
bash scripts/install_openclaw_linux.sh
```

如果希望手动执行，等价核心命令是：

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
openclaw --version
openclaw onboard --install-daemon
```

首次 onboarding 时配置一个可用的模型提供商。模型提供商密钥只进入 OpenClaw 的服务端配置，不写入 StayScape 前端和 Git 仓库。

### 开启 Responses API

云端执行：

```bash
openclaw config set --batch-json '[
  {"path":"gateway.mode","value":"local"},
  {"path":"gateway.bind","value":"lan"},
  {"path":"gateway.http.endpoints.responses.enabled","value":true}
]'
openclaw gateway restart
openclaw gateway status --json
curl -fsS http://127.0.0.1:18789/healthz
curl -fsS http://127.0.0.1:18789/readyz
```

这里的 `lan` 是为了让 Docker 中的 FastAPI 能访问同一台主机上的 Gateway；不要因此在阿里云安全组放行 18789。Gateway 的共享 Token 通过下面命令在云端查看，绝不要粘贴到聊天或提交到 Git：

```bash
openclaw gateway auth-token --show
```

把 Token 写入 `/opt/StayScape/.env` 的 `OPENCLAW_GATEWAY_TOKEN`。官方 Gateway 文档也建议使用 Token 鉴权并通过 systemd 管理长期运行进程。[OpenClaw Gateway 官方文档](https://docs.openclaw.ai/gateway)

## 五、安装 StayScape 两个 Skill

在云服务器上把两个 ZIP 解压到当前 OpenClaw workspace：

```bash
mkdir -p "$HOME/.openclaw/workspace/skills/stayscape-product-generator"
mkdir -p "$HOME/.openclaw/workspace/skills/stayscape-visitor-matcher"
unzip -o dist/stayscape-product-generator.zip \
  -d "$HOME/.openclaw/workspace/skills/stayscape-product-generator"
unzip -o dist/stayscape-visitor-matcher.zip \
  -d "$HOME/.openclaw/workspace/skills/stayscape-visitor-matcher"
```

如果 ZIP 不在云服务器，可以在本地执行：

```powershell
scp dist\stayscape-product-generator.zip root@<ECS公网IP>:/opt/StayScape/dist/
scp dist\stayscape-visitor-matcher.zip root@<ECS公网IP>:/opt/StayScape/dist/
```

Skill 负责产品创意、主题、推荐解释和营销表达；库存、成本、售价、毛利、容量、天气和状态仍由 StayScape FastAPI 规则引擎决定，符合赛题要求。

## 六、一键启动 StayScape

在 `/opt/StayScape`：

```bash
bash scripts/deploy_aliyun.sh
```

脚本会：

1. 检查 Docker 和 Compose v2；
2. 创建并保护 `.env`；
3. 自动生成缺失的 `SECRET_KEY` 和 PostgreSQL 密码；
4. 构建 Vue、FastAPI 和 Nginx 镜像；
5. 启动 PostgreSQL；
6. 执行 Alembic migration 和一次幂等演示 Seed；
7. 等待 `/health` 通过后显示容器状态。

部署成功后访问：

```text
http://<ECS公网IP>/
```

演示账号：

- 酒店：`hotel_demo / StayScape123!`
- 商户：`merchant_craft / StayScape123!`

确认数据库已有正式数据后，可以把 `.env` 改成：

```env
SEED_DEMO_ON_STARTUP=false
```

然后执行：

```bash
docker compose --env-file .env up -d
```

生产环境的 `/api/v1/demo/reset` 和 `/api/v1/demo/seed` 会被后端拒绝，不会被游客调用重置数据。

## 七、Windows Hub 连接云端 Gateway（可选）

网站使用不需要 Windows Hub。如果要在 Windows 桌面客户端查看同一个云端 Agent，推荐 SSH 隧道，不直接公开 18789：

```powershell
ssh -N -L 18789:127.0.0.1:18789 <SSH用户>@<ECS公网IP>
```

保持这个窗口运行，然后在 Windows Hub 的远程 Gateway/连接设置中填写本机地址 `127.0.0.1:18789` 和云端 Gateway Token。OpenClaw 官方远程访问文档使用同样的 `LocalForward 18789:127.0.0.1:18789` 方案；Windows Hub 支持远程 Gateway URL、Token 和 SSH 隧道连接。[OpenClaw 远程访问](https://docs.openclaw.ai/gateway/remote) · [OpenClaw Windows Hub](https://docs.openclaw.ai/windows)

这条 SSH 隧道只服务于 Windows Hub，不影响游客访问 StayScape，也不需要修改 StayScape 的 `OPENCLAW_BASE_URL`。

## 八、赛题演示顺序

1. 打开公网网站，游客端展示 12+ 个城市文旅产品；
2. 登录酒店端 Product Studio，选择 `FAMILY + RAIN`，生成多个候选；
3. 展示 `OpenClaw LIVE`、Skill 名称、trace_id 和 `fallback=false`；
4. 模拟发布后打开游客端产品详情，查看主题图、社媒文案、SVG 海报和旅行咨询；
5. 商户把非遗名额从 12 改成 4；
6. 打开 Dynamic Operations，展示产品从 4 套变为 1 套并进入 `LOW_STOCK`；
7. 游客端刷新后显示“仅剩 1 套”；
8. 在 Skill 调用日志中核对 Provider、transport、agent_id、trace_id 和 fallback 状态。

如果 OpenClaw 尚未配置好模型或 Gateway，先将 `AGENT_PROVIDER=mock`，仍可完成全部确定性业务演示；页面会明确显示 Mock Fallback，不会冒充真实 OpenClaw 调用。

## 九、常用运维命令

```bash
# 查看 StayScape
docker compose --env-file .env ps
docker compose --env-file .env logs -f server

# 更新代码并重建
git pull --ff-only origin main
docker compose --env-file .env up -d --build

# 查看 OpenClaw
openclaw gateway status --json
openclaw gateway health
openclaw doctor

# 停止/启动 StayScape
docker compose --env-file .env down
docker compose --env-file .env up -d
```

不要执行 `docker compose down -v`，否则会删除 PostgreSQL 数据卷。
