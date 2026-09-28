# 余宿成景：临期客房文旅运营 Skill

## 目标

余宿成景服务一家固定杭州酒店：先识别未来 24 至 48 小时未售房的经营机会，
再结合最近经营聚合、天气、已审核合作资源和带来源的杭州文旅知识，生成少量
可计算、可校验、待人工确认的产品候选。它不替代 OTA、支付、订单结算或多酒店
PMS。

## 运行链路

    酒店经营者自然语言任务
      -> yusuchengjing-hotel-ops
      -> stayscape_analyze_hotel_opportunity
      -> FastAPI 事实快照
      -> stayscape_create_product_proposal
      -> Product Generator + 确定性规则
      -> PENDING_CONFIRMATION
      -> 经营者明确确认
      -> 草稿或发布

天气、合作名额、服务或客房变化时，经营者可要求复核；系统调用
stayscape_recheck_product_health，重新计算容量、价格边界和状态。该动作可以
下调、替换已审核资源或暂停产品，但不会自行发布新产品。

## 事实与创意的边界

| 层 | 负责内容 |
| --- | --- |
| FastAPI / PostgreSQL | 房型、服务、合作资源、容量、成本、价格、毛利、年龄、时间、状态、事务与人工确认 |
| 余宿成景 Tool | 事实性机会分析、经营聚合、天气来源、知识库来源与候选方向 |
| Product Generator Skill | 主题、商品命名、访客表达、视觉 brief |
| Marketing Writer Skill | 已验证产品的海报 brief、社交文案与短视频脚本 |
| Visitor Matcher Skill | 已发布产品的轻量问一问匹配和解释 |

公共 POI 永远是 PUBLIC_REFERENCE：只能做带来源路线建议，不能参与库存、成本、
毛利、产品权益或预订承诺。

## 独立、可复现版本

可直接打包的目录是 skills/yusuchengjing-hotel-ops。它包含结构化 JSON 测试
数据、标准库 Python 计算器、JSON Schema、示例和单元测试：

    cd skills/yusuchengjing-hotel-ops
    python scripts/run_workflow.py --date 2026-09-12 --count 2
    python -m unittest discover -s tests -v

它的演示数据均带 competition_test_data 标记。项目组上线前需替换固定酒店
画像、真实合作资源、实时库存和已核验文旅资料；不得把示例价格、地址、容量或
合作关系当成真实业务信息。

## 知识库治理

当前杭州知识库覆盖博物馆、美术馆、科技馆、自然湿地、乐园、演艺、运河、历史
街区、图书馆和城市漫游等 25 个公共参考点。每条记录均有来源 URL、最后核验
时间和 verification_status。默认状态为 VERIFY_REQUIRED，因此 Agent 必须提示
信息需确认，不能把开放时间、预约或票务说成已确认事实。

建议在比赛前由项目组每周核验：

1. 地址、开放时间、闭馆日与预约说明。
2. 来源页面是否可访问。
3. 资源是否已成为真实、已签约、带日期和容量的 PartnerResource。
4. 是否应将过期记录标记为 STALE 或下线。

## 参考的工程模式

- [携程问道 tripai-skill](https://github.com/trips-ai/tripai-skill)：使用完整自然语言查询，但保留受控外部事实入口。
- [TourMind Booking Skills](https://github.com/tourmind-com/Tourmind-Booking-Skills)：候选价格不当作最终预订事实；关键动作前必须复核并显式确认。
- [TripSmart](https://github.com/zhao11122233/tourism-agent)：将自然语言解析、约束匹配和可验证的业务阶段拆开。
- [VoyageMind](https://github.com/smyjl15/tourism-agent)：把可复现评测和测试场景作为产品质量证据，而不是替代业务功能。
- [HotelIQ](https://github.com/karan00190/HotelIQ_Revenue_Management_Platform)：区分实时数据工具和概念知识，避免由模型猜测经营数字。
- [inPMS](https://github.com/inhotel-io/inpms)：保留人工掌控、可审计决定和确定性经营闸门。

这些项目仅提供工程思路参考；StayScape 不复制它们的业务代码或接入其数据。
