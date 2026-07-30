# StayScape 演示脚本

## 启动

本地后端：

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

浏览 `http://localhost:5173`，后端文档在 `http://localhost:8000/docs`。

## 主闭环

1. 进入酒店经营端，账号 `hotel_demo / StayScape123!`。
2. 打开“智能组包”，选择亲子房、家庭早餐（3份/套）、延迟退房（1份/套）、室内非遗手作（3个名额/套），天气选择 RAIN、预算 700、最低毛利率 20%、价格锚点 599。
3. 生成结果应为：4套、成本455元、售价599元、毛利144元、毛利率约24.04%。
4. 点击模拟发布，然后进入“游客H5预览”，填写2成人+1名6岁儿童、预算700、手工兴趣、花生过敏，查看推荐、时间安排和预约意向。
5. 用 `merchant_craft / StayScape123!` 进入商户端，把室内非遗手作体验从12改为4，原因填“其他渠道已预约8人”。酒店端产品应自动变为1套、LOW_STOCK。
6. 把该资源暂停，系统会在同类资源中尝试替换儿童茶文化课堂；若没有满足日期、天气、客群、容量和毛利约束的替代资源，则暂停原产品。

## 新增功能演示

### 多方案与天气个性化

1. 在“智能组包”中把“生成候选数量”设为3，填写“偏亲子研学”或“偏茶文化”等创意方向。
2. 分别切换 RAIN、SUNNY、CLOUDY，资源选择会按天气标签和客群适配实时过滤；每个方案会生成不同的产品定位、推荐理由、营销标题和素材。
3. 进入任一产品详情，点击“编辑产品”，可以修改产品名称、入住日期、天气、主题和营销内容；天气/日期变化会再次触发确定性库存、时间、替代资源和毛利校验。

### 文旅营销素材

产品详情的“文旅营销素材智能生成”会生成：

- 酒店大堂 / 小红书封面的 SVG 图文海报；
- 小红书 / 朋友圈长文案；
- 30 秒短视频分镜脚本；
- OTA / 前台卖点卡。

点击“重新生成素材”可留下 Skill 调用日志和新的 trace_id。

### 商户资源维护

商户进入“我的文旅资源”后可以新增资源名称、类别、日期、起止场次、名额、结算价、适龄范围、天气标签、地址和预约规则；编辑日期或场次后，引用该资源的酒店产品会立即重算。

### 自然语言游客推荐

游客在“个性化推荐”文本框直接输入：

```text
一家三口带一个6岁孩子，预算700元，明天下雨，喜欢非遗手工，下午四点体验，孩子花生过敏。
```

系统会返回“已理解的需求”，再按真实库存、天气、年龄、时段、预算和过敏风险筛选套餐，并展示住宿、餐饮、文化体验时间线和有限调整建议。

### 产品池管理与经营总览

经营总览的临期客房、可组包资源、在售产品和预约意向指标均可点击；资源快照和产品卡片可进入详情。酒店可从“当前产品池”编辑、发布、暂停或删除产品。

## API 快速验证

```powershell
$login = Invoke-RestMethod http://localhost:8000/api/v1/auth/login -Method Post -ContentType 'application/json' -Body '{"username":"hotel_demo","password":"StayScape123!"}'
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod http://localhost:8000/api/v1/hotel/dashboard -Headers $headers
Invoke-RestMethod http://localhost:8000/api/v1/visitor/products
```

## 重置演示数据

开发环境可执行：

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/demo/reset -Method Post
```

该接口会清空演示业务数据并重新创建默认酒店、账号、客房、服务和合作资源；生产环境会拒绝调用。
