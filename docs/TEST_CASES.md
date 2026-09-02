# 可复现测试案例

运行基础回归：

```bash
python -m pytest apps/server/tests -q
npm --prefix apps/web run build
```

| 编号 | 操作 | 预期结果 |
|---|---|---|
| TC-01 | 酒店端“AI 运营任务”输入“周六亲子博物馆产品，预算 700，生成 3 套” | 系统读取实时库存、天气、近 14 天聚合与知识库，返回 `PENDING_CONFIRMATION` 候选；页面展示 Agent、Skill、工具、知识库、fallback 和耗时的可审计步骤，不展示内部推理。 |
| TC-02 | 对候选选择“加入草稿” | 产品转为 `DRAFT`，游客端不展示。 |
| TC-03 | 对候选选择“确认发布” | FastAPI 再次校验库存、资源、时间、年龄、天气、成本和毛利；通过后转 `ON_SALE`/`LOW_STOCK`，否则返回明确错误。 |
| TC-04 | 飞书 allowlist 酒店经营者提出相同任务，再回复“确认发布第 1 个” | 同一个酒店任务记录被复用；飞书和 Web 看到相同候选与确认状态；客服角色只能查询，不能确认。 |
| TC-05 | 查询一个 `VERIFY_REQUIRED` 的博物馆知识项 | 返回来源和“信息需确认”；Agent 不把开放时间或预约当成已确认事实，也不把它当作可售资源。 |
| TC-06 | 断开天气服务或请求超出预报窗口 | 返回 `VERIFY_REQUIRED` 提示，系统不伪造天气事实。 |
| TC-07 | 酒店端产品详情点击“生成宣传素材” | 调用营销 Skill；勾选主图时调用服务器 `.env` 中配置的 Wan 模型，SVG 文本层与 AI 主图分离；API Key 不进入浏览器。 |
| TC-08 | Wan CDN 返回 `application/octet-stream` 但图片字节为 JPEG/PNG/WebP | 后端按文件签名保存；非图片、SVG 或超限文件被拒绝。 |
| TC-09 | 游客在产品详情“问一问”询问“还有室内体验吗？” | Visitor Skill 仅从当前上架、有余量产品中返回可点击替代卡片，不创建产品、不锁库存、不生成多日行程。 |
| TC-10 | 访问旧 `/visitor/trip-plans/*` | 返回 404；前端没有自定义多日组包路由或 API。 |
| TC-11 | 酒店端选择“博物馆看展”与“两大一小”，生成 3 套候选 | 每套产品持久化 `party_size=3`；早餐和按人计名额均按 3 人校验，超过房型人数或名额时给出可执行提示。 |
| TC-12 | 对多套候选输入“统一改得更适合带 6 岁孩子” | 调用 Marketing Skill 批量重写游客可见文案与 SVG 海报；默认不重做主图，勾选后才调用 Wan；库存、价格与发布状态不改变。 |
| TC-13 | 首次访问未上传图片的资源卡，再次访问同一资源卡 | 首次显示轻量占位并缓存服务端检索到的公开参考图；后续命中浏览器重定向缓存与服务器文件缓存。上传实拍图始终优先。 |

Live 验证还需检查 `bash scripts/deploy.sh live` 的 `/v1/responses` smoke test、`openclaw skills check --agent stayscape-main --json` 和飞书 WebSocket channel 状态。真实飞书 App Secret、allowlist 和百炼 Key 仅填写服务器 `.env`，不纳入仓库或截图。
