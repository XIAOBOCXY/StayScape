# 测试报告基础内容

## 已覆盖

- 容量规则：6/30/6/12 和每套1/3/1/3 得4套；体验名额4得1套；0消耗量拒绝。
- 金额规则：455成本、599售价、144毛利、约24.04%毛利率；最低毛利率20%和预算不足错误。
- API：登录、角色边界、产品生成、模拟发布、商户容量变化、游客推荐、预约意向。
- Agent：JSON格式修复、超时降级、trace_id与skill_call_logs。
- 前端：`npm run build`，TypeScript和Vite构建通过。
- Skill：`quick_validate.py`校验通过，ZIP根目录包含`SKILL.md`。

## 执行命令

```powershell
.venv\Scripts\python.exe -m pytest apps/server/tests -q
npm.cmd --prefix apps/web run build
.venv\Scripts\python.exe scripts/package_skills.py
```

## 运行时验收

Docker环境执行 `docker compose up -d --build`，然后访问 `http://localhost:8080`；本地环境按 `docs/DEMO.md`执行。

