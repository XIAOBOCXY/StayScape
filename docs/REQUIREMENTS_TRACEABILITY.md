# JBGS-2026-06 StayScape 需求追溯

StayScape 聚焦两项可落地核心功能：

1. 酒店临期库存驱动的文旅产品智能生成与动态运营
2. 游客对酒店已审核产品的“问一问”咨询、解释和替代推荐

## 需求与实现映射

| 业务要求 | StayScape 证据 |
|---|---|
| 场景适配性 | 临期房、早餐、延迟退房、合作体验名额、天气、场次、商户状态和游客预约形成真实经营闭环 |
| 功能实用性 | 酒店 Web/飞书多轮运营任务、待确认候选、营销素材、游客问一问、预约意向和 12→4→1 动态联动 |
| 部署便捷性 | Windows 本地 SQLite/Mock、Docker Compose PostgreSQL、阿里云 `scripts/deploy.sh live` 一键部署 |
| 引擎技术实现 | ECS 唯一 `stayscape-main` Agent、正式 `/v1/responses`、余宿成景总控与三个专用 Skill、飞书 Tool Plugin、文旅知识库、天气和经营数据工具 |
| 代码规范性 | FastAPI 分层、SQLAlchemy/Alembic、Pydantic Schema、确定性规则、四个 Skill 和 OpenClaw Tool Plugin |
| 异常处理能力 | Agent 超时重试、JSON Schema 修复、Live 不伪装 fallback、资源/天气/时间/年龄/容量/毛利校验、知识过期显式提示、统一错误结构 |
| 文档完整性 | README、API、架构、业务调研、测试案例、演示脚本、OpenClaw、飞书、阿里云部署、ClawHive Skill 上传说明 |

## AI 与规则边界

AI/Skill 负责主题创意、资源语义选择、产品命名、营销内容、视觉 brief、游客理解和推荐解释。FastAPI/PostgreSQL/规则引擎负责真实资源 ID、库存、成本、售价、毛利、状态、天气、日期、年龄、容量、预约和事务。文旅知识库只提供带来源的参考，未核验信息明确提示“信息需确认”。任何 Agent 输出都会被后端重新校验；酒店必须确认候选后才能变成草稿或游客可见产品。

## 可观测产品指标

- 亲子房 6、早餐 30、延迟退房 6、非遗名额 12，消耗 1/3/1/3，生成 4 套
- 成本 455 元、售价 599 元、毛利 144 元、毛利率约 24.04%
- 商户把非遗名额改成 4，产品变为 1 套、状态 `LOW_STOCK`
- 游客输入人数、儿童年龄、预算、天气、时间、兴趣和负向偏好，前端确认后再推荐
- `FAMILY`、`COUPLE`、`FRIENDS`、`SOLO`、`LOCAL_WEEKEND` 与 `RAIN`、`SUNNY`、`CLOUDY` 均由资源池和规则生成差异化方案

## 安全与数据导出

Gateway Token、Tool Token、模型凭证和飞书 App Secret 只存在服务端环境变量；浏览器只访问 StayScape API。公网只开放 80/443，数据库、FastAPI 和 Gateway 不直接暴露。Skill ZIP 可独立导出并上传 ClawHive，不包含密钥或业务数据库。
