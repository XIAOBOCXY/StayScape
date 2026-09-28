# 把 StayScape 的 Skill 上传到 ClawHive

StayScape 的正式运行时是自托管 OpenClaw。ClawHive（SkillHub）用于**发布和托管 Skill 包**：
在平台上展示、审核、分发给其它 Agent 使用，不承担业务运行时的角色。

## 1. 生成上传包

```powershell
.venv\Scripts\python.exe scripts/package_skills.py
```

输出在 `dist/`：

| 文件 | 用途 |
| --- | --- |
| `yusuchengjing-hotel-ops.zip` | 酒店临期库存运营总控 Skill（推荐上传这个） |
| `stayscape-product-generator.zip` | 产品候选生成与校验 |
| `stayscape-visitor-matcher.zip` | 游客咨询与推荐匹配 |
| `stayscape-marketing-writer.zip` | 营销素材文案 |
| `stayscape-clawhive-chat.zip` | ClawHive 游客/运营自然语言入口，查询产品并生成待确认候选 |
| `stayscape-skills-bundle.zip` | 五个 Skill 打成一包，便于整体下载分发 |

每个 zip 的**根目录**就是 `SKILL.md`（不是套一层文件夹），这是平台校验的关键。

## 2. 在 ClawHive 上使用

1. 打开 ClawHive / SkillHub 控制台（`https://skills.netease.im`），用组织账号登录。
2. 进入 **Skill 管理 → 上传 Skill**，选择 `dist/yusuchengjing-hotel-ops.zip`。
3. 平台会解析 `SKILL.md` 的 `name`、`description` 与 `{baseDir}` 资源；确认名称后提交审核，审核通过即可在 Skill 市场检索到。
4. 在需要使用的 Agent / 会话中**启用该 Skill**，需要组合能力时再勾选另外三个。
5. Skill 本身只描述工作流与约束，真正的数据读写通过 StayScape 的工具插件完成：Agent 侧要能访问 `stayscape-openclaw-plugin`（工具清单见 `docs/OPENCLAW.md`），插件再回连 StayScape API。

## 3. 上传前自检

- ZIP 根目录直接包含 `SKILL.md`，frontmatter 至少有 `name`、`description`，且 `name` 与目录名一致。
- 不包含 `.env`、Token、API Key、`node_modules`、缓存或本地数据库（打包脚本会自动跳过并校验）。
- Skill 不返回互联网图片 URL：视觉部分输出 `visual_brief` / `creative_angle` / `poster_style`，图片由 StayScape 媒体系统与 Wan 生图服务负责。
- 单个 zip 不超过 50 MB。

## 4. 两种 Skill 运行边界

StayScape 现在明确分成两种入口：

1. **网站运行时 Skill**：由 StayScape 自托管 OpenClaw 加载 `yusuchengjing-hotel-ops`、`stayscape-product-generator`、`stayscape-visitor-matcher` 和 `stayscape-marketing-writer`。这条链路可以读写 StayScape 的受控业务工具，但发布、库存、价格和数据库状态仍由 FastAPI 与确定性校验负责。
2. **ClawHive 对话 Skill**：`skills/stayscape-clawhive-chat` 是独立的游客/运营对话入口，适合上传到另一个 Agent/ClawHive。它不需要数据库账号、JWT、OpenClaw Gateway Token 或 MCP；只需要 `StayScape Server URL` 和网页端生成的 `Agent API Token`，调用 `/api/v1/agent-tools/me`、`/api/v1/agent-tools/visitor/products/search` 和受控的 `/api/v1/agent-tools/hotel/products/generate`。生成只会创建 `PENDING_CONFIRMATION` 候选，不能发布、改库存或改价格。

### ClawHive 对话 Skill 的接入步骤

1. 登录 StayScape 酒店后台，进入 **设置 → Agent 接入**，创建 Token。原文只在创建成功时显示一次，数据库只保存 SHA-256 hash；Token 自动绑定当前登录账号和当前酒店。
2. 在 ClawHive 上传 `dist/stayscape-clawhive-chat.zip`，或者安装 `stayscape-skills-bundle.zip` 后只启用 `stayscape-clawhive-chat`。
3. 在 Agent 的 Skill 配置中填写：

   ```text
   StayScape Server URL: https://你的域名
   Agent API Token: 创建时复制的 stsc_live_... 字符串
   ```

4. 先调用 `GET /api/v1/agent-tools/me` 测试连接，再由 Skill 调 `POST /api/v1/agent-tools/visitor/products/search` 查询，或调用 `POST /api/v1/agent-tools/hotel/products/generate` 生成候选。请求体不需要也不允许决定 `hotel_id`；服务端从 Token 绑定关系中确定酒店，并只返回/生成该酒店的数据。
5. Token 泄露或不再使用时，在 **设置 → Agent 接入** 点击撤销；撤销立即使 `/me`、产品查询和候选生成返回 401。

ClawHive Skill 与网站运行时 Skill 的关系是“共享业务 API、分开运行时”：ClawHive 不会进入网站的 OpenClaw 对话链，也不会拿到数据库凭据或 JWT。

### 添加新的酒店账号

不要把密码写入 `apps/server/app/seed.py` 或提交到 Git。服务器上使用一次性环境变量调用：

```bash
cd /opt/StayScape
docker compose --env-file .env exec -T \
  -e OPERATOR_USERNAME=new_operator \
  -e OPERATOR_PASSWORD='在终端临时输入的强密码' \
  -e HOTEL_ID=3 server python /app/scripts/create_hotel_user.py
```

脚本位于 `scripts/create_hotel_user.py`，会校验用户名唯一、酒店有效和密码长度；创建完成后不保存明文密码。当前线上保留的演示账号仍是 `hotel_demo`；新账号 `operations_admin` 不是 Seed 账号、没有演示密码，但为保证接入演示能够立即读到产品，当前绑定的是已有酒店 3，因此会继承该酒店已有产品。若要完全空白的租户，应先新增酒店记录，再把 `HOTEL_ID` 指向该酒店。

## 5. 运行时链路

```text
StayScape Web/H5 -> FastAPI -> self-hosted OpenClaw -> stayscape-main -> Skill
Feishu           -> OpenClaw Feishu Channel -> stayscape-main -> Skill/Tool -> FastAPI
```

ClawHive 不参与网站的 OpenClaw 调用链，因此网站端不需要配置 `AGENT_PROVIDER=clawhive`、`CLAWHIVE_BASE_URL`、`CLAWHIVE_AGENT_ID`。只有安装独立的 `stayscape-clawhive-chat` 时，外部 Agent 才需要配置 StayScape Server URL 与 Agent API Token。

## 6. 模型与生图

- 语言模型：DeepSeek（`deepseek/deepseek-v4-flash`，认证 profile `deepseek:default`），由 OpenClaw 网关调用。
- 生图：Wan 图像服务（`WAN_IMAGE_MODEL=wan2.7-image`），只在运营端点击「生成宣传素材」时触发。
- 两个凭证都通过服务器环境变量注入，不会写进 Skill 包，也不会出现在任何对话回复里。

## 7. 两种用法：要不要连数据库，可以自己选

先回答那个最容易搞混的问题：**可以完全不用数据库，只用 Skill 包里自带的知识库数据，也能在 ClawHive 里用**。区别只是能做的事有多少。

### 用法 A：只上传 Skill，不连任何数据库（离线知识库模式）

`yusuchengjing-hotel-ops.zip` 的根目录里有一个 `data/` 目录，里面是随包带走的**静态数据快照**：

| 文件 | 内容 | 不连数据库时能做什么 |
| --- | --- | --- |
| `data/tourism_knowledge.json` | 文旅知识库（地点、开放时间、预约提示、来源），就是工作台「文旅知识库」的离线副本 | 讲解地点、规划参考路线、回答「哪里适合亲子/下雨天去哪」 |
| `data/room_inventory.json` | 房型、日期、余量、成本 | 估算某天还能组几套、哪类房紧张 |
| `data/partner_resources.json` | 合作体验、名额、结算价 | 挑可用体验、做候选搭配 |
| `data/hotel_services.json` / `recent_sales.json` / `weather.json` | 酒店服务、近期需求、天气 | 把方案和天气、需求信号对齐 |

只用这些文件就能在任意 Claw 里跑完整条离线流程：

```bash
python scripts/run_workflow.py --date 2026-09-28        # 一次性产出候选方案 + 校验结果
python scripts/analyze_inventory.py                     # 只看房态压力
python scripts/search_resources.py --keyword 夜游        # 只看可用体验
```

**不需要填任何 API Key，也不需要数据库。** 你只要把 zip 传到 ClawHive、在会话里启用它，然后直接问「杭州有哪些适合亲子的室内地点」「按 built-in 数据给 9 月 28 日排一套双人方案」即可。

这个模式做不到的事：读实时房态、真实下单/占位、把产品真正发布进 StayScape 工作台、AI 生图。这些属于用法 B。

### 用法 B：Skill + StayScape 后端（推荐，功能完整）

在用法 A 之上，再给它一个 StayScape 的地址和工具令牌，Agent 就能通过工具插件读写真实数据：

```text
Agent(别的 Claw) --工具调用--> stayscape-openclaw-plugin
                                   |
                                   v
                        FastAPI /api/v1/agent-tools
                                   |
                                   v
                 PostgreSQL（docker volume: stayscape_pgdata）
```

具体步骤：

1. 部署一个可被访问的 StayScape 实例（见第 8 节），确认 `/health` 返回 200。
2. 在别的 Claw 里安装 `stayscape-openclaw-plugin` 工具插件，并启用需要的 Skill。
3. 打开 StayScape 工作台 → **API 设置**：点「填入当前预设」把当前生效的网关地址与模型名带入表单，再补上该环境的工具令牌、模型/生图 Key 后保存。
4. 需要迁移或备份时点 **导出数据**（已修复导出接口），会把房态、资源、产品、订单与知识库导成一个 JSON；把其中的 `knowledge` 部分同步回 `data/tourism_knowledge.json` 就能刷新离线快照。

缺网关地址/工具令牌/模型 Key 时，Agent 会自动回落到用法 A 的离线数据，不会假装读到了真实库存。

## 8. 知识库数据到底存放在哪

- 随包副本：`skills/yusuchengjing-hotel-ops/data/tourism_knowledge.json`，上传到 ClawHive 时就在包里，离线可用。
- 服务端权威副本：PostgreSQL 的 `travel_knowledge` 表（工作台「文旅知识库」页可以增改、按来源复核），通过 `GET /api/v1/hotel/knowledge` 或工具 `stayscape_search_travel_knowledge` 读取。
- 两者关系：包内 JSON 是快照；服务端改了知识库后，用第 6 节的导出步骤刷新快照，再 `python scripts/package_skills.py` 重新打包上传即可。

## 9. 本地部署与数据安全

```bash
# 离线演示（不调用外部模型，零费用）
bash scripts/deploy.sh demo

# 正式链路（OpenClaw + Qwen/DeepSeek + Wan 生图）
bash scripts/deploy.sh live
```

- 两个模式都通过工作台的「API 设置」读取当前配置，密钥只写服务器本地文件，不回显明文、不进 Skill 包。
- 数据（含运行期配置 `runtime-settings.json`）都落在 `runtime/generated-media` 与 `stayscape_pgdata` 卷上，容器重建不丢；导出 JSON 可在迁移/交接时脱敏核对。
