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
