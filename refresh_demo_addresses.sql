UPDATE partner_resources AS resource
SET address = CASE resource.resource_name
    WHEN '室内非遗手作体验' THEN '杭州市拱墅区小河路334号杭州工艺美术博物馆手工艺活态馆入口'
    WHEN '丝绸手作体验' THEN '杭州市拱墅区小河路334号杭州工艺美术博物馆手工艺活态馆入口'
    WHEN '儿童茶文化课堂' THEN '杭州市西湖区龙井路88号中国茶叶博物馆双峰馆区体验厅入口'
    WHEN '宋韵点茶体验' THEN '杭州市西湖区龙井路88号中国茶叶博物馆双峰馆区体验厅入口'
    WHEN '江南香囊制作' THEN '杭州市西湖区龙井路88号中国茶叶博物馆双峰馆区体验厅入口'
    WHEN '良渚文明探索体验' THEN '杭州市余杭区美丽洲路1号良渚博物院入口'
    WHEN '城市博物馆主题导览' THEN '杭州市上城区粮道山18号杭州博物馆正门'
    WHEN '杭州博物馆开放式导览' THEN '杭州市上城区粮道山18号杭州博物馆正门'
    WHEN '亲子科学探索实验室' THEN '杭州市拱墅区西湖文化广场2号浙江省科技馆入口'
    WHEN '南山路看展漫游' THEN '杭州市上城区南山路218号中国美术学院美术馆入口'
    WHEN '湘湖轻户外探索' THEN '杭州市萧山区湘湖路132号湘湖国家旅游度假区游客中心'
    WHEN '钱塘江沿线骑行' THEN '杭州市上城区之江东路杭州城市阳台钱塘江绿道入口'
    WHEN '湖滨夜市美食漫游' THEN '杭州市上城区东坡路10号杭州湖滨银泰in77D区入口'
    WHEN '咖啡漫游体验' THEN '杭州市上城区东坡路10号杭州湖滨银泰in77D区入口'
    WHEN '西湖晨间城市漫步' THEN '杭州市上城区龙井路1号西湖景区湖滨三公园集合点'
    WHEN '西湖夜景漫游' THEN '杭州市上城区龙井路1号西湖景区湖滨三公园集合点'
    WHEN '城市夜景旅拍' THEN '杭州市拱墅区环城北路208号武林门码头游客入口'
    WHEN '运河亲子旅拍' THEN '杭州市拱墅区环城北路208号武林门码头游客入口'
    WHEN '运河夜游' THEN '杭州市拱墅区环城北路208号武林门码头游客入口'
    WHEN '室内儿童乐园' THEN '杭州市拱墅区萍水街丰潭路380号城西银泰城2层MELAND CLUB入口'
    WHEN '动物互动体验' THEN '杭州市西湖区文二西路777号西溪国家湿地公园北门游客中心'
    WHEN '西溪湿地亲子探索' THEN '杭州市西湖区文二西路777号西溪国家湿地公园北门入口'
    WHEN '植物观察自然课堂' THEN '杭州市西湖区桃源岭1号杭州植物园正门'
    WHEN '室内攀岩体验' THEN '杭州市萧山区博奥路2657号1层1-D102号杭州PARTYDAY运动超乐场入口'
    WHEN '卡丁车周末场' THEN '杭州市萧山区博奥路2657号1层1-D102号杭州PARTYDAY运动超乐场入口'
    WHEN '室内射箭体验' THEN '杭州市萧山区博奥路2657号1层1-D102号杭州PARTYDAY运动超乐场入口'
    WHEN '青年运动馆体验' THEN '杭州市萧山区博奥路2657号1层1-D102号杭州PARTYDAY运动超乐场入口'
    WHEN '杭帮菜双人体验' THEN '杭州市上城区仁和路83号知味观仁和店入口'
    WHEN '江南甜品制作' THEN '杭州市上城区凤凰山路9号中国杭帮菜博物馆钱塘厨房体验区入口'
    WHEN '音乐现场小剧场' THEN '杭州市上城区新业路39号杭州大剧院可变剧场入口'
    WHEN '双人陶艺体验' THEN '杭州市上城区南复路60号南宋官窑博物馆陶艺体验入口'
    WHEN '沉浸式城市演出' THEN '杭州市西湖区之江路148号杭州宋城入口'
    WHEN '宋韵演出' THEN '杭州市西湖区之江路148号杭州宋城入口'
    WHEN '儿童剧周末场' THEN '杭州市拱墅区湖墅南路136号浙话艺术剧院入口'
    WHEN '杭州乐园公开信息' THEN '杭州市萧山区风情大道2555号杭州乐园正门'
    WHEN '西湖博物馆公开导览' THEN '杭州市上城区南山路89号杭州西湖博物馆正门'
    ELSE resource.address
END,
booking_notice = CASE
    WHEN resource.booking_notice LIKE '%实时场次以商户确认结果为准%' THEN '请按页面场次提前10分钟到场，儿童体验由同行成年人陪同。'
    ELSE resource.booking_notice
END,
cancellation_rule = CASE
    WHEN resource.cancellation_rule LIKE '%以商户确认结果为准%' THEN '体验前24小时可申请改期。'
    ELSE resource.cancellation_rule
END
FROM merchants AS merchant
WHERE resource.merchant_id = merchant.id
  AND merchant.hotel_id = 3
  AND resource.resource_name IN (
      '室内非遗手作体验', '丝绸手作体验', '儿童茶文化课堂', '宋韵点茶体验', '江南香囊制作',
      '良渚文明探索体验', '城市博物馆主题导览', '杭州博物馆开放式导览', '亲子科学探索实验室',
      '南山路看展漫游', '湘湖轻户外探索', '钱塘江沿线骑行', '湖滨夜市美食漫游', '咖啡漫游体验',
      '西湖晨间城市漫步', '西湖夜景漫游', '城市夜景旅拍', '运河亲子旅拍', '运河夜游',
      '室内儿童乐园', '动物互动体验', '西溪湿地亲子探索', '植物观察自然课堂', '室内攀岩体验',
      '卡丁车周末场', '室内射箭体验', '青年运动馆体验', '杭帮菜双人体验', '江南甜品制作',
      '音乐现场小剧场', '双人陶艺体验', '沉浸式城市演出', '宋韵演出', '儿童剧周末场',
      '杭州乐园公开信息', '西湖博物馆公开导览'
  );

UPDATE public_resources
SET address = '杭州市上城区南山路89号杭州西湖博物馆正门'
WHERE resource_name = '西湖博物馆';

INSERT INTO hotel_services (
    hotel_id, service_name, service_type, available_date, available_quantity,
    unit_cost, reference_price, start_time, end_time, suitable_crowds,
    replaceable, image_url, image_source, image_attribution, status, created_at, updated_at
)
SELECT
    3, '行李寄存', 'LUGGAGE_STORAGE', day::date, 100,
    5.00, 20.00, '08:00'::time, '22:00'::time, 'ALL',
    true, '', '', '', 'AVAILABLE', now(), now()
FROM generate_series(date '2026-09-29', date '2026-10-15', interval '1 day') AS days(day)
WHERE NOT EXISTS (
    SELECT 1 FROM hotel_services existing
    WHERE existing.hotel_id = 3
      AND existing.service_type = 'LUGGAGE_STORAGE'
      AND existing.available_date = day::date
      AND existing.status = 'AVAILABLE'
);
