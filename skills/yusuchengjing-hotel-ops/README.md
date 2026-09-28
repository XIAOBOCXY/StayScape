# 余宿成景 OpenClaw Skill

余宿成景是一个单酒店、临期客房驱动的文旅产品运营 Skill。它先读取
库存、近期经营、天气和已审核合作资源，再生成可验证的候选产品；它不是
普通旅行问答、OTA 搜索或自动发布工具。

## 两种运行方式

### StayScape 生产部署

StayScape 已把这个 Skill 安装给唯一的 stayscape-main Agent。飞书中可直接
说：

    分析明天的临期库存，生成今天最值得推的两个产品

Agent 先调用受限的事实工具，随后只创建待人工确认的候选。经营者必须明确
说 加入草稿 或 确认发布，系统才会写入共享平台数据。浏览器、飞书消息和
Git 仓库都不会看到 API Key、Gateway Token 或 Tool Token。

### 独立本地演示

本目录不依赖数据库或 SaaS。Python 3.11+ 即可运行：

    cd skills/yusuchengjing-hotel-ops
    python scripts/run_workflow.py --date 2026-09-12 --count 2
    python -m unittest discover -s tests -v

所有示例库存、价格、合作资源和地址均是 competition_test_data，不代表真实
酒店库存、价格或商业合作。真实酒店上线前必须替换 references/hotel-profile.md
及 data 目录中的对应文件，并重新核验公开文旅信息。

## 文件与数据职责

- data/room_inventory.json：临期房型总量、余量、最低售价和成本。
- data/hotel_services.json：酒店自营服务与可组包数量。
- data/recent_sales.json：去标识化的最近经营漏斗聚合。
- data/partner_resources.json：仅已审核合作资源才可能进入正式权益。
- data/weather.json：天气输入；生产系统应替换为带来源的实时预报。
- data/tourism_knowledge.json：带来源与核验状态的公共路线参考，默认不可售。
- data/products.json：仅保存 validation.status 为 PASS 的审核后候选。

## 常用确定性命令

每个命令仅向 stdout 写 JSON；失败同样返回结构化 JSON。

    python scripts/analyze_inventory.py
    python scripts/analyze_demand.py
    python scripts/search_resources.py --input "{\"date\":\"2026-09-12\",\"target_segment\":\"情侣/双人客\",\"party_size\":2,\"weather\":\"小雨\"}"
    python scripts/recheck_products.py --date 2026-09-12

## 测试

测试覆盖库存压力、需求、容量瓶颈、财务下限、验证器错误码、替代资源筛选、
保存闸门，以及天气/名额变化后的复核。若项目环境已安装 pytest，也可以运行：

    pytest -q tests

## 已知边界

- 这是单酒店演示 Skill，不含支付、OTA、真实订单结算或多酒店租户。
- 公共 POI 只用于路线建议，不能被当成套餐权益或库存。
- 图像模型不可用时，Skill 输出可校验的 poster brief 与 prompt，不伪造图片。
- 真实开放时间、预约、票务和交通信息必须由运营人员或自动刷新任务依据来源
  核验；过期记录应显示 信息需确认。
