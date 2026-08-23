# StayScape 余宿成景

StayScape 是面向酒店临期客房的文旅业务系统：FastAPI + PostgreSQL 保存真实经营数据，确定性规则计算库存、成本、售价、毛利和状态；OpenClaw 只负责调用两个 StayScape Skill 完成产品创意、游客理解、文案和解释。

## 产品定位

- 酒店临期库存驱动的文旅产品生成与动态运营
- 游客自然语言需求驱动的个性化旅居匹配
- Web/H5 和飞书是两个入口，但只使用一个 OpenClaw Gateway、一个 Agent：`stayscape-main`
- ClawHive 仅用于 Skill 发布、管理、验证和展示；不作为 StayScape 的运行时 API

```text
Visitor H5  -> FastAPI -> OpenClaw -> stayscape-main -> stayscape-visitor-matcher
Hotel Web   -> FastAPI -> OpenClaw -> stayscape-main -> stayscape-product-generator
Feishu      -> OpenClaw Feishu Channel -> stayscape-main -> StayScape Tools -> FastAPI
```

## 核心演示不变量

演示 Seed 始终保留：亲子房 6 间、家庭早餐 30 份、延迟退房 6 份、室内非遗手作 12 个名额；每套消耗 1/3/1/3，因此最终可售 4 套。成本为 `220 + 15×3 + 10 + 60×3 = 455` 元，建议售价 599 元，单套毛利 144 元，毛利率约 24.04%。商户把手作名额改为 4 后，产品自动变为 1 套并进入 `LOW_STOCK`。

## 本地 Windows 开发

```powershell
Copy-Item .env.example .env
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r apps/server/requirements.txt
.venv\Scripts\python.exe -m alembic -c apps/server/alembic.ini upgrade head
.venv\Scripts\python.exe scripts/seed_demo.py

# Terminal 1
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/server --reload --port 8000

# Terminal 2
npm.cmd --prefix apps/web install --cache apps/web/.npm-cache
npm.cmd --prefix apps/web run dev
```

访问 `http://localhost:5173`；API 文档为 `http://localhost:8000/docs`。默认酒店账号为 `hotel_demo / StayScape123!`，商户账号示例为 `merchant_craft / StayScape123!`。

## Docker Demo

无需模型密钥即可演示完整业务闭环：

```bash
cp .env.example .env
bash scripts/deploy.sh demo
```

Windows 若已安装 Docker Desktop，也可以执行 `docker compose up -d --build`，入口默认是 `http://localhost:8080`。

## 阿里云公网 Live 部署

在 Ubuntu 22.04/24.04 或阿里云 Linux ECS 上：

```bash
git clone https://github.com/XIAOBOCXY/StayScape.git
cd StayScape
cp .env.example .env
# 在 .env 中填写模型供应商配置；飞书凭证可选
bash scripts/deploy.sh live
```

### 下载后在哪里填写 API 和密钥

所有密钥只填写在**项目根目录的本机 `.env` 文件**中：

- 下载 ZIP 后：先解压，再进入同时包含 `README.md` 和 `.env.example` 的解压目录；API 填在该目录的 `.env`
- 本地克隆后：`<项目根目录>/.env`
- 部署到 ECS 后：`/opt/StayScape/.env`

例如，下载 ZIP 后请在解压目录执行；不要在 GitHub 网页、前端页面或任何源码文件中填写 Key：

```bash
cd <解压后的 StayScape 目录>
cp .env.example .env
nano .env
```

先从模板创建并限制权限：

```bash
cd /opt/StayScape
cp .env.example .env
chmod 600 .env
nano .env
```

当前仓库固定的 OpenClaw `2026.6.9` 已实测 `qwen/qwen3.5-plus`；不要在此固定版本中填写 `qwen/qwen3.7-plus`。

使用 Qwen + OpenClaw 的 Live 模式时，填写以下配置；`QWEN_API_KEY` 替换为你自己在阿里云百炼创建的真实 Standard API Key：

```env
MODE=live
AGENT_PROVIDER=openclaw
OPENCLAW_BASE_URL=http://openclaw:18789
OPENCLAW_AGENT_TARGET=openclaw/default
OPENCLAW_PRIMARY_MODEL=qwen/qwen3.5-plus
QWEN_API_KEY=<你的百炼 Standard API Key>
FEISHU_ENABLED=false
```

飞书不是 Web/H5 的启动前置条件。如需启用飞书，再在同一个 `.env` 中填写：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_DM_ALLOW_FROM`、`FEISHU_GROUP_ALLOW_FROM`、`FEISHU_GROUP_SENDER_ALLOW_FROM`、`FEISHU_OPERATOR_ALLOW_FROM` 和 `FEISHU_SUPPORT_ALLOW_FROM`。

不要把真实 Qwen Key、飞书 Secret、Gateway Token、Tool Token 或数据库密码写进 README、源码、前端、Dockerfile、Skill ZIP，或提交到 GitHub。项目的 `.gitignore` 会排除 `.env`；部署脚本会在服务器端生成 `SECRET_KEY`、PostgreSQL 密码、Gateway Token 和 Tool Token。

脚本会生成服务端密钥、PostgreSQL 密码、Gateway Token 和 Tool Token，构建 PostgreSQL、FastAPI、Vue、Nginx 以及固定版本的官方 OpenClaw 镜像，安装两个 Skill、Qwen provider、可选 Feishu plugin 和 StayScape Tool Plugin，执行迁移、幂等 Seed、健康检查、Skill/plugin discovery、模型清单检查和一次真实 `/v1/responses` smoke test。Live 模式需要把 `QWEN_API_KEY` 预先写入服务器 `.env`；模型供应商首次授权仍需人工完成一次。

公网只开放 80/443；不要开放 18789、5432、8000。详细步骤见 [docs/DEPLOY_ALIYUN.md](docs/DEPLOY_ALIYUN.md)、[docs/OPENCLAW.md](docs/OPENCLAW.md) 和 [docs/FEISHU.md](docs/FEISHU.md)。

## 测试与打包

```powershell
.venv\Scripts\python.exe -m pytest apps/server/tests -q
npm.cmd --prefix apps/web run build
.venv\Scripts\python.exe scripts/package_skills.py
```

两个 ZIP 位于 `dist/stayscape-product-generator.zip` 和 `dist/stayscape-visitor-matcher.zip`，ZIP 根目录直接包含 `SKILL.md`，打包脚本会排除 `.env`、密钥、`node_modules`、缓存和构建产物。

## 目录

- `apps/server`：FastAPI、SQLAlchemy、Alembic、规则引擎、Agent 编排和业务 API
- `apps/web`：酒店 Web、商户端和游客 H5
- `skills`：两个可上传 ClawHive 的 Skill
- `integrations/stayscape-openclaw-plugin`：官方 OpenClaw Tool Plugin
- `deploy/openclaw`：固定版本 OpenClaw 容器和配置模板
- `scripts`：本地 Seed、Skill 打包、demo/live 一键部署
- `docs`：架构、赛题对齐、OpenClaw、飞书和阿里云部署说明
