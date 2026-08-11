# 阿里云 ECS 公网部署

本方案把 StayScape、PostgreSQL、Nginx 和一个固定版本的官方 OpenClaw Gateway 部署在同一台 Linux ECS。浏览器只访问 Nginx；FastAPI 通过 Docker 内网调用 Gateway，Gateway 不公开到公网。

## 1. 购买和准备 ECS

在阿里云 ECS 控制台创建 Linux x64 实例，比赛演示建议至少 4 vCPU / 8 GB / 80 GB SSD，选择 Ubuntu 22.04/24.04 LTS 或阿里云 Linux。购买公网 IPv4，并在安全组只放行：

| 端口 | 来源 | 用途 |
|---|---|---|
| 22/TCP | 你的固定办公 IP（临时调试可短时放宽） | SSH |
| 80/TCP | `0.0.0.0/0` | HTTP 网站 |
| 443/TCP | `0.0.0.0/0` | HTTPS 网站 |

禁止放行 18789、5432、8000 和 8080。正式域名、HTTPS 证书和中国内地公网域名备案按阿里云当前流程办理。

## 2. 登录并安装 Docker

```bash
ssh root@<ECS公网IP>
apt-get update
apt-get install -y ca-certificates curl git openssl
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker --version
docker compose version
```

也可以使用阿里云镜像/云助手安装 Docker，但必须确认 Docker Compose v2 可用。

## 3. 拉取代码并配置

```bash
mkdir -p /opt
cd /opt
git clone https://github.com/XIAOBOCXY/StayScape.git
cd StayScape
cp .env.example .env
chmod 600 .env
```

编辑 `.env`：

```env
MODE=live
AGENT_PROVIDER=openclaw
OPENCLAW_MODEL=openclaw/default
```

`scripts/deploy.sh live` 会自动生成 `SECRET_KEY`、PostgreSQL 密码、`OPENCLAW_GATEWAY_TOKEN` 和 `STAYSCAPE_AGENT_TOOL_TOKEN`。如果模型供应商需要 API Key/OAuth，请按该供应商要求把凭证配置在 OpenClaw 的服务端运行环境中；不要提交到 Git。

飞书不是 Web/H5 启动条件。需要飞书时再填写 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_DM_ALLOW_FROM` 和 `FEISHU_GROUP_ALLOW_FROM`。

## 4. 一键部署

```bash
bash scripts/deploy.sh live
```

脚本会：

1. 检查 Docker/Compose，必要时只有显式设置 `INSTALL_DOCKER=true` 才执行官方 Docker bootstrap
2. 初始化并保护 `.env`
3. 生成私密 Token
4. 渲染不入 Git 的 OpenClaw 配置
5. 构建 PostgreSQL、FastAPI、Vue、Nginx 和官方 `ghcr.io/openclaw/openclaw:2026.6.6-slim`
6. 启动 Alembic、幂等演示 Seed、单 Agent `stayscape-main`、两个 Skill 和 Tool Plugin
7. 通过 `openclaw skills list --agent stayscape-main --json` 检查两个 Skill
8. 只有发现成功后才把 FastAPI 的 Live Agent readiness 标记为 true

访问 `http://<ECS公网IP>/`。默认酒店演示账号为 `hotel_demo / StayScape123!`。确认演示数据后，把 `SEED_DEMO_ON_STARTUP=false` 写入 `.env`，再执行：

```bash
docker compose --env-file .env --profile live up -d server
```

## 5. HTTPS

比赛现场可以先使用公网 IP 的 HTTP。正式域名按阿里云证书/备案流程配置 443，并在 Nginx 前增加 HTTPS 终止。不要为了让浏览器访问而把 Gateway 端口映射出来。

## 6. 运维命令

```bash
docker compose --env-file .env --profile live ps
docker compose --env-file .env --profile live logs -f server
docker compose --env-file .env --profile live logs -f openclaw
docker compose --env-file .env --profile live up -d --build
docker compose --env-file .env --profile live down
```

不要使用 `docker compose down -v`，否则会删除 PostgreSQL 和 OpenClaw 持久化卷。

## 7. NOT VERIFIED 项

本地开发机没有可用 Docker Engine、阿里云 ECS SSH 凭证、模型供应商凭证或飞书 App Secret，因此本地只能验证配置/代码契约，不能在本轮实际完成公网部署、模型调用或飞书消息闭环。部署到你的 ECS 后应保存 `/health`、Skill discovery、产品生成和飞书日志作为比赛验收证据。
