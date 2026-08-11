# ClawHive 使用边界

StayScape 的正式运行时是自托管 OpenClaw，不是 ClawHive 云端实例。此前尝试的 ClawHive Agent bridge 没有可供 FastAPI 稳定调用的第三方 Invoke API，因此项目已移除 `CLAWHIVE_*` 配置、ClawHive provider 和 bridge 主链路。

ClawHive 在本项目中保留三个用途：

1. 上传和发布 `stayscape-product-generator`、`stayscape-visitor-matcher` 两个 Skill ZIP
2. 在 SkillHub 中展示、管理和验证 Skill
3. 作为比赛生态材料的一部分，证明 Skill 符合平台上传规范

生成 ZIP：

```powershell
.venv\Scripts\python.exe scripts/package_skills.py
```

上传前检查：

- ZIP 根目录直接包含 `SKILL.md`
- frontmatter 至少有 `name`、`description`
- 不包含 `.env`、Token、API Key、`node_modules`、缓存或本地数据库
- Skill 不返回互联网图片 URL；视觉建议使用 `visual_brief`、`creative_angle`、`poster_style`，图片由 StayScape 媒体系统和后端海报渲染负责

运行时链路为：

```text
StayScape Web/H5 -> FastAPI -> self-hosted OpenClaw -> stayscape-main -> Skill
Feishu           -> OpenClaw Feishu Channel -> stayscape-main -> Skill/Tool
```

因此不要再填写 `AGENT_PROVIDER=clawhive`、`CLAWHIVE_BASE_URL`、`CLAWHIVE_AGENT_ID` 等旧变量，也不要把 ClawHive 实例 ID、VM ID 或客户端实例 ID 当作 HTTP Agent 路由地址。
