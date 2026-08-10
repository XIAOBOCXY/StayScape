# StayScape 余宿成景

面向酒店临期客房的库存驱动型文旅产品智能生成与动态运营系统。

StayScape 不把临期房简单降价清仓，而是根据房型库存、酒店服务、合作文旅资源、天气、目标客群、预算和最低毛利率，生成“客房 + 酒店服务 + 杭州文化体验”的主题住宿产品；资源名额、服务、房量或价格变化后，系统会在事务内自动重算库存、成本、售价、毛利和产品状态。

## 核心演示结果

演示数据：亲子房6间、早餐30份、延迟退房6份、室内非遗体验12个名额；每套消耗1/3/1/3，因此可售4套。成本为220+45+10+180=455元，政策价格锚点599元，单套毛利144元，毛利率约24.04%。商户将体验名额改为4后，产品自动变成1套并标记为库存紧张。

每次演示 Seed 还会在不改变上述主链路的前提下，补充 9 种房型、24 项酒店服务、10 家合作商户和 30 项文旅资源，覆盖主题乐园、亲子探索、运动、夜游、旅拍、美食、自然、演出、城市漫游和文化体验等类别，并生成至少 12 个来自同一规则引擎的在售展示产品。资源带有来源类型、天气、适龄、场次、状态和组包许可约束；`PUBLIC_REFERENCE` 仅用于展示参考，不会进入正式组包。

## 技术栈

当前版本还支持商户完整维护资源名称、日期和起止场次；酒店产品池可编辑、删除产品；一次生成多套差异化方案；产品详情生成 SVG 图文海报、社媒文案、短视频脚本和门店卖点卡；游客可以直接用自然语言描述人数、预算、天气、兴趣、时间和过敏信息获取推荐。

- 前端：Vue 3、TypeScript、Vite、Vue Router、Pinia、Axios、Element Plus、Vant、ECharts依赖。
- 后端：Python 3.11、FastAPI、SQLAlchemy 2.x、Pydantic 2.x、Alembic、Pytest、WebSocket。
- 数据库：本地 SQLite；Docker 使用 PostgreSQL 16。
- Agent：Mock Agent 离线可运行；OpenClaw HTTP 适配器支持环境变量切换，并带超时、重试、JSON修复、Schema校验和降级。
- 部署：Docker Compose + Nginx。

## 本地启动（Windows）

```powershell
Copy-Item .env.example .env
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r apps/server/requirements.txt
.venv\Scripts\python.exe -m alembic -c apps/server/alembic.ini upgrade head
.venv\Scripts\python.exe scripts/seed_demo.py

# 终端一：
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/server --reload --port 8000

# 终端二：
npm.cmd --prefix apps/web install --cache apps/web/.npm-cache
npm.cmd --prefix apps/web run dev
```

如果本机 npm 用户缓存没有权限，使用项目内的 `--cache apps/web/.npm-cache`；不会修改系统环境。也可以直接执行 `scripts/dev.ps1`。

访问：

- 游客H5：http://localhost:5173
- API文档：http://localhost:8000/docs
- 默认酒店账号：`hotel_demo / StayScape123!`
- 默认商户账号：`merchant_craft / StayScape123!`、`merchant_tea / StayScape123!`、`merchant_photo / StayScape123!`

## Docker启动

```powershell
docker compose up -d --build
```

入口为 http://localhost:8080。Compose会启动 PostgreSQL、FastAPI、Vue静态站点和Nginx；后端容器执行 Alembic migration 与演示 Seed。停止：

```powershell
docker compose down
```

## 测试与打包

```powershell
.venv\Scripts\python.exe -m pytest apps/server/tests -q
npm.cmd --prefix apps/web run build
.venv\Scripts\python.exe scripts/package_skills.py
```

生成两个可上传文件：`dist/stayscape-product-generator.zip` 和 `dist/stayscape-visitor-matcher.zip`。两个 ZIP 的根目录都直接包含 `SKILL.md`，不含密钥、`.env`、`node_modules`、`__pycache__`。

## Agent配置

默认 `AGENT_PROVIDER=mock`，无需外部服务即可完成完整演示。接入OpenClaw时通过 `.env`设置：

```env
AGENT_PROVIDER=openclaw
OPENCLAW_BASE_URL=https://your-openclaw-endpoint
OPENCLAW_API_KEY=从环境变量注入
OPENCLAW_MODEL=openclaw/default
```

真实密钥只放在本地环境或部署平台密钥管理中，不提交仓库。无论使用哪种Agent，最终数字和数据状态都由后端规则引擎决定。

## 演示数据重置

开发环境调用 `POST /api/v1/demo/reset`，或者运行：

```powershell
.venv\Scripts\python.exe scripts/reset_demo.py
```

更多演示步骤见 [docs/DEMO.md](docs/DEMO.md)，架构边界见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。
赛题对齐说明见 [docs/CONTEST_ALIGNMENT.md](docs/CONTEST_ALIGNMENT.md)。

#
