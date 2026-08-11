# StayScape 比赛演示脚本

## 1. 启动

本地 Demo 不需要模型凭证：

```powershell
Copy-Item .env.example .env
.venv\Scripts\python.exe -m alembic -c apps/server/alembic.ini upgrade head
.venv\Scripts\python.exe scripts/seed_demo.py
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/server --reload --port 8000
```

另开终端启动前端：

```powershell
npm.cmd --prefix apps/web run dev
```

打开 `http://localhost:5173`。Docker Demo 直接使用 `docker compose --profile demo up -d --build`。

## 2. 主链路：临期库存生成产品

1. 登录酒店端：`hotel_demo / StayScape123!`。
2. 打开 Product Studio，选择亲子家庭房、家庭早餐（每套 3 份）、延迟退房（每套 1 份）和室内非遗手作（每套 3 个名额）。
3. 选择 `RAIN`、预算 700、最低毛利率 20%、价格锚点 599，并生成 1 个候选。
4. 规则引擎应得到：6 间房、30 份早餐、6 份延迟退房、12 个体验名额，最终库存 `min(6,10,6,4)=4` 套。
5. 单套成本为 `220 + 15×3 + 10 + 60×3 = 455` 元，售价 599 元，毛利 144 元，毛利率约 24.04%。
6. 模拟发布后打开游客 H5，产品卡和详情会展示主题媒体、旅行灵感、SVG 海报、体验图库、咨询和预约入口。

## 3. 主链路：实时动态运营

1. 在商户端找到室内非遗手作，把剩余名额从 12 改为 4。
2. 酒店 Dynamic Operations 页面应显示 `4 套 → 1 套`，状态从 `ON_SALE` 变为 `LOW_STOCK`。
3. 游客端刷新后应显示“仅剩 1 套”。底层资源和已占用库存由同一事务更新，后续重算不会恢复到 4 套。
4. 停用该资源后，系统只会从合法、日期/天气/年龄/容量/毛利均满足的已允许资源中寻找替代；找不到时暂停产品。

## 4. 主链路：游客自然语言推荐

在游客推荐页输入：

```text
两大两小，孩子6岁和9岁，预算1000，下午三点到，下雨，孩子喜欢玩，不想喝茶。
```

系统先返回需求确认卡。用户可以直接把成人数量改为 3、修改儿童年龄、预算、天气、兴趣、负向偏好、到店时间和饮食/过敏信息，再提交推荐。提交请求以用户确认字段为最高优先级，不会再次用原话解析结果覆盖手动修改。

推荐结果必须同时满足人数、房型最大入住人数、天气、儿童年龄、活动时间、预算、库存和负向偏好过滤；Visitor Skill 只负责解释“为什么适合”。

## 5. Feishu / OpenClaw 现场演示

Live 模式使用同一个 `stayscape-main` Agent：

```text
酒店经理：明天还有哪些临期亲子房？杭州下雨，预算700左右，帮我做一个适合一家三口的产品。
Agent：调用 stayscape_get_hotel_context → Product Skill → 返回候选草稿。
酒店经理：创建这个草稿。
Agent：调用 stayscape_create_product_draft → FastAPI 校验 → 返回产品 ID 和 Web URL。
客服：2大1小，孩子6岁，下雨，预算700，不喝茶，有什么推荐？
Agent：调用 stayscape_list_available_products → Visitor Skill → 返回不含茶资源的合法产品。
```

酒店日志中应能对应看到 `Provider=OPENCLAW`、`Agent=stayscape-main`、入口、Skill、trace、Schema、fallback 和耗时。

## 6. 重置

仅开发环境可调用：

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/demo/reset -Method Post
```

公网部署不应暴露该接口；生产恢复应通过受控运维流程完成。
