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

