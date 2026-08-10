"""Rich, deterministic Hangzhou demo catalog used by the local showcase.

The first four partner resources and first three rooms/services are kept in
``seed.py`` because the competition's main 4-to-1 inventory demonstration
depends on their order and numbers.  Everything in this module is appended to
that baseline so the catalogue can grow without changing the acceptance case.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.security import hash_password
from .models import HotelService, Merchant, PartnerResource, RoomInventory, User


EXTRA_MERCHANTS = [
    ("merchant_themepark", "杭州城市乐园体验中心", "THEME_PARK", "何老师", "ACTIVE"),
    ("merchant_nature", "西溪自然探索机构", "NATURE", "宋老师", "ACTIVE"),
    ("merchant_sport", "城市青年运动馆", "SPORT", "陆教练", "ACTIVE"),
    ("merchant_food", "江南味觉体验馆", "FOOD", "许老师", "ACTIVE"),
    ("merchant_nightlife", "钱塘夜游与娱乐空间", "NIGHTLIFE", "叶老师", "ACTIVE"),
    ("merchant_performance", "杭州城市演艺空间", "PERFORMANCE", "沈老师", "ACTIVE"),
    ("merchant_reference", "杭州公共文旅信息站", "PUBLIC_REFERENCE", "资料中心", "TERMINATED"),
]


def _room(hotel_id: int, target_date: date, *, room_type: str, count: int, normal: str, minimum: str, cost: str, max_guests: int, features: str, crowds: str, tags: str, status: str = "AVAILABLE") -> RoomInventory:
    return RoomInventory(
        hotel_id=hotel_id,
        room_type=room_type,
        available_date=target_date,
        available_count=count,
        normal_price=Decimal(normal),
        minimum_price=Decimal(minimum),
        accounting_cost=Decimal(cost),
        max_guests=max_guests,
        features=features,
        suitable_crowds=crowds,
        tags=tags,
        status=status,
    )


def _service(hotel_id: int, target_date: date, *, name: str, service_type: str, quantity: int, cost: str, reference: str, crowds: str = "ALL", start: time | None = None, end: time | None = None, replaceable: bool = True, status: str = "AVAILABLE") -> HotelService:
    return HotelService(
        hotel_id=hotel_id,
        service_name=name,
        service_type=service_type,
        available_date=target_date,
        available_quantity=quantity,
        unit_cost=Decimal(cost),
        reference_price=Decimal(reference),
        start_time=start,
        end_time=end,
        suitable_crowds=crowds,
        replaceable=replaceable,
        status=status,
    )


def _resource(merchant_id: int, target_date: date, *, name: str, category: str, description: str, start: time, end: time, capacity: int, settlement: str, market: str, crowds: str, minimum_age: int | None, maximum_age: int | None, indoor: bool, weather: str, address: str, source_type: str = "PARTNER", package_enabled: bool = True, status: str = "AVAILABLE") -> PartnerResource:
    return PartnerResource(
        merchant_id=merchant_id,
        resource_name=name,
        category=category,
        description=description,
        available_date=target_date,
        start_time=start,
        end_time=end,
        remaining_capacity=capacity,
        settlement_price=Decimal(settlement),
        market_price=Decimal(market),
        suitable_crowds=crowds,
        minimum_age=minimum_age,
        maximum_age=maximum_age,
        indoor=indoor,
        weather_tags=weather,
        address=address,
        booking_notice="请按场次提前10分钟到场，儿童体验需由同行成年人陪同。",
        cancellation_rule="体验前24小时可申请改期，实时场次以商户确认结果为准。",
        package_enabled=package_enabled,
        source_type=source_type,
        status=status,
    )


def seed_extra_catalog(db: Session, hotel_id: int, target_date: date, *, demo_password: str) -> dict[str, int]:
    """Append the rich catalogue to a freshly created demo hotel."""

    users = {item.username: item for item in db.scalars(select(User).where(User.role == "MERCHANT")).all()}
    for index, (username, merchant_name, category, contact, cooperation_status) in enumerate(EXTRA_MERCHANTS, start=4):
        if username in users:
            continue
        user = User(username=username, password_hash=hash_password(demo_password), role="MERCHANT")
        db.add(user)
        db.flush()
        db.add(
            Merchant(
                hotel_id=hotel_id,
                user_id=user.id,
                merchant_name=merchant_name,
                category=category,
                contact_name=contact,
                contact_phone=f"138001380{index:02d}",
                cooperation_status=cooperation_status,
            )
        )
    db.flush()

    merchants = {
        user.username: user.merchant
        for user in db.scalars(select(User).where(User.role == "MERCHANT")).all()
        if user.merchant and user.merchant.hotel_id == hotel_id
    }

    db.add_all(
        [
            _room(hotel_id, target_date, room_type="湖景大床房", count=2, normal="699", minimum="559", cost="280", max_guests=2, features="落地窗、湖景、纪念日欢迎卡", crowds="COUPLE", tags="湖景,旅拍,纪念日"),
            _room(hotel_id, target_date, room_type="城市景观房", count=8, normal="539", minimum="429", cost="230", max_guests=2, features="城市天际线、办公桌、咖啡角", crowds="COUPLE,SOLO,LOCAL_WEEKEND", tags="城市,咖啡,独处"),
            _room(hotel_id, target_date, room_type="家庭套房", count=2, normal="899", minimum="699", cost="350", max_guests=5, features="双卧布局、儿童阅读角、家庭客厅", crowds="FAMILY", tags="家庭,儿童,大空间"),
            _room(hotel_id, target_date, room_type="庭院主题房", count=2, normal="759", minimum="599", cost="300", max_guests=3, features="江南庭院、茶席、安静露台", crowds="COUPLE,LOCAL_WEEKEND,SOLO", tags="庭院,茶席,慢生活"),
            _room(hotel_id, target_date, room_type="影音娱乐房", count=4, normal="639", minimum="499", cost="250", max_guests=4, features="投影、影音会员、桌游收纳", crowds="COUPLE,FRIENDS", tags="电影,桌游,朋友出行"),
            _room(hotel_id, target_date, room_type="亲子联通房", count=2, normal="829", minimum="629", cost="320", max_guests=4, features="相邻双空间、儿童阅读角、家庭储物", crowds="FAMILY", tags="家庭,儿童,联通房"),
        ]
    )
    db.add_all(
        [
            _service(hotel_id, target_date, name="欢迎龙井茶", service_type="WELCOME_TEA", quantity=12, cost="5", reference="28", crowds="FAMILY,COUPLE,SOLO", start=time(14, 0), end=time(18, 0)),
            _service(hotel_id, target_date, name="双人欢迎饮品", service_type="WELCOME_DRINK", quantity=8, cost="8", reference="36", crowds="COUPLE,FRIENDS", start=time(15, 0), end=time(22, 0)),
            _service(hotel_id, target_date, name="儿童洗漱包", service_type="KIDS_AMENITY", quantity=6, cost="4", reference="15", crowds="FAMILY", start=time(15, 0), end=time(23, 0)),
            _service(hotel_id, target_date, name="儿童拖鞋", service_type="KIDS_AMENITY", quantity=6, cost="3", reference="12", crowds="FAMILY", start=time(15, 0), end=time(23, 0)),
            _service(hotel_id, target_date, name="亲子手作材料包", service_type="CRAFT_KIT", quantity=8, cost="12", reference="35", crowds="FAMILY", replaceable=True),
            _service(hotel_id, target_date, name="夜间甜汤", service_type="NIGHT_DESSERT", quantity=10, cost="8", reference="28", crowds="ALL", start=time(20, 0), end=time(22, 0)),
            _service(hotel_id, target_date, name="客房夜宵", service_type="ROOM_SNACK", quantity=10, cost="22", reference="58", crowds="COUPLE,FRIENDS,LOCAL_WEEKEND", start=time(21, 0), end=time(23, 0)),
            _service(hotel_id, target_date, name="双人下午茶", service_type="AFTERNOON_TEA", quantity=8, cost="28", reference="88", crowds="COUPLE,LOCAL_WEEKEND", start=time(14, 0), end=time(17, 0)),
            _service(hotel_id, target_date, name="城市文化地图", service_type="CITY_MAP", quantity=20, cost="2", reference="12", crowds="ALL"),
            _service(hotel_id, target_date, name="西湖漫游路线卡", service_type="CITY_ROUTE", quantity=15, cost="3", reference="18", crowds="COUPLE,SOLO,LOCAL_WEEKEND"),
            _service(hotel_id, target_date, name="城市摄影路线卡", service_type="PHOTO_ROUTE", quantity=10, cost="3", reference="18", crowds="COUPLE,FRIENDS,SOLO", start=time(10, 0), end=time(20, 0)),
            _service(hotel_id, target_date, name="儿童旅行任务卡", service_type="KIDS_TASK", quantity=8, cost="2", reference="15", crowds="FAMILY"),
            _service(hotel_id, target_date, name="雨具借用", service_type="RAIN_GEAR", quantity=5, cost="6", reference="20", crowds="ALL", start=time(8, 0), end=time(22, 0)),
            _service(hotel_id, target_date, name="自行车租借", service_type="BIKE_RENTAL", quantity=4, cost="15", reference="60", crowds="COUPLE,FRIENDS,LOCAL_WEEKEND", start=time(8, 0), end=time(20, 0)),
            _service(hotel_id, target_date, name="影音会员", service_type="MEDIA_PASS", quantity=5, cost="12", reference="35", crowds="COUPLE,FRIENDS"),
            _service(hotel_id, target_date, name="桌游借用", service_type="BOARD_GAME", quantity=4, cost="10", reference="38", crowds="COUPLE,FRIENDS", status="SUSPENDED"),
            _service(hotel_id, target_date, name="生日布置", service_type="BIRTHDAY_SETUP", quantity=2, cost="80", reference="260", crowds="FAMILY,COUPLE", status="SUSPENDED"),
            _service(hotel_id, target_date, name="情侣纪念日布置", service_type="ANNIVERSARY_SETUP", quantity=2, cost="100", reference="320", crowds="COUPLE"),
            _service(hotel_id, target_date, name="客房茶席", service_type="ROOM_TEA_SETUP", quantity=3, cost="25", reference="88", crowds="COUPLE,SOLO,LOCAL_WEEKEND", start=time(16, 0), end=time(18, 0)),
            _service(hotel_id, target_date, name="运动能量包", service_type="SPORT_SNACK", quantity=6, cost="8", reference="30", crowds="FRIENDS,COUPLE,LOCAL_WEEKEND"),
        ]
    )
    db.flush()

    resource_rows = [
        _resource(merchants["merchant_craft"].id, target_date, name="丝绸手作体验", category="CULTURE", description="在轻量工作坊完成一件杭州丝绸小物，适合第一次来杭州的家庭与情侣。", start=time(13, 0), end=time(14, 30), capacity=16, settlement="55", market="108", crowds="FAMILY,COUPLE", minimum_age=5, maximum_age=70, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="拱宸桥丝绸工坊"),
        _resource(merchants["merchant_tea"].id, target_date, name="江南香囊制作", category="CULTURE", description="把江南香气装进一只可带走的香囊，适合亲子与文化兴趣游客。", start=time(14, 30), end=time(16, 0), capacity=16, settlement="58", market="108", crowds="FAMILY,COUPLE,SOLO", minimum_age=5, maximum_age=70, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="西湖茶事体验馆"),
        _resource(merchants["merchant_photo"].id, target_date, name="城市夜景旅拍", category="PHOTO", description="摄影师带领游客记录运河灯影与城市夜色，交付一组轻旅拍照片。", start=time(19, 0), end=time(20, 30), capacity=12, settlement="110", market="198", crowds="COUPLE,FRIENDS", minimum_age=12, maximum_age=70, indoor=False, weather="SUNNY,CLOUDY", address="京杭大运河灯影段"),
        _resource(merchants["merchant_themepark"].id, target_date, name="杭州乐园亲子欢乐体验", category="THEME_PARK", description="以家庭友好的游乐设施和互动任务组成的一日体验，属于比赛 Demo 合作名额。", start=time(10, 0), end=time(17, 0), capacity=30, settlement="150", market="238", crowds="FAMILY", minimum_age=3, maximum_age=70, indoor=False, weather="SUNNY,CLOUDY", address="杭州乐园 Demo 合作区", source_type="DEMO"),
        _resource(merchants["merchant_themepark"].id, target_date, name="主题乐园家庭日票", category="THEME_PARK", description="家庭日票与酒店服务组合，适合晴天的亲子一日游。", start=time(10, 0), end=time(18, 0), capacity=24, settlement="135", market="218", crowds="FAMILY", minimum_age=3, maximum_age=70, indoor=False, weather="SUNNY,CLOUDY", address="杭州乐园 Demo 合作区", source_type="DEMO"),
        _resource(merchants["merchant_themepark"].id, target_date, name="夜场乐园体验", category="THEME_PARK", description="日落后进入乐园，适合年轻情侣与朋友把夜晚过得更有参与感。", start=time(18, 30), end=time(21, 30), capacity=20, settlement="128", market="208", crowds="COUPLE,FRIENDS", minimum_age=12, maximum_age=70, indoor=False, weather="SUNNY,CLOUDY", address="杭州乐园夜场 Demo 区", source_type="DEMO"),
        _resource(merchants["merchant_themepark"].id, target_date, name="室内儿童乐园", category="KIDS", description="雨天也能玩的室内儿童乐园，设置分龄游戏区与亲子互动时段。", start=time(15, 0), end=time(17, 0), capacity=24, settlement="90", market="168", crowds="FAMILY", minimum_age=3, maximum_age=12, indoor=True, weather="RAIN,CLOUDY", address="城西室内儿童乐园"),
        _resource(merchants["merchant_nature"].id, target_date, name="动物互动体验", category="NATURE", description="在自然教育老师带领下近距离观察小动物，强调温和互动。", start=time(10, 0), end=time(11, 30), capacity=18, settlement="82", market="148", crowds="FAMILY", minimum_age=4, maximum_age=60, indoor=False, weather="SUNNY,CLOUDY", address="西溪自然教育基地"),
        _resource(merchants["merchant_nature"].id, target_date, name="西溪湿地亲子探索", category="NATURE", description="沿湿地步道完成亲子观察任务，适合晴天的自然探索家庭。", start=time(9, 0), end=time(11, 0), capacity=15, settlement="75", market="138", crowds="FAMILY", minimum_age=5, maximum_age=65, indoor=False, weather="SUNNY,CLOUDY", address="西溪湿地北门"),
        _resource(merchants["merchant_nature"].id, target_date, name="植物观察自然课堂", category="NATURE", description="用一堂轻自然课认识杭州的植物与季节，适合亲子、独行和慢游客群。", start=time(14, 0), end=time(15, 30), capacity=12, settlement="60", market="118", crowds="FAMILY,SOLO,LOCAL_WEEKEND", minimum_age=6, maximum_age=70, indoor=False, weather="SUNNY,CLOUDY", address="杭州植物观察园"),
        _resource(merchants["merchant_sport"].id, target_date, name="室内攀岩体验", category="SPORT", description="教练带领完成入门攀岩线路，雨天也能保持运动感。", start=time(16, 0), end=time(17, 30), capacity=12, settlement="88", market="158", crowds="FRIENDS,COUPLE", minimum_age=12, maximum_age=60, indoor=True, weather="RAIN,CLOUDY,SUNNY", address="城市青年运动馆"),
        _resource(merchants["merchant_sport"].id, target_date, name="卡丁车周末场", category="SPORT", description="朋友或情侣一起挑战短赛道，适合想要刺激一点的周末。", start=time(19, 0), end=time(20, 0), capacity=2, settlement="118", market="198", crowds="FRIENDS,COUPLE", minimum_age=12, maximum_age=60, indoor=True, weather="RAIN,CLOUDY,SUNNY", address="钱江卡丁车馆"),
        _resource(merchants["merchant_sport"].id, target_date, name="室内射箭体验", category="SPORT", description="教练指导下完成室内射箭挑战，适合朋友组队和年轻情侣。", start=time(15, 0), end=time(16, 0), capacity=10, settlement="78", market="138", crowds="FRIENDS,COUPLE", minimum_age=12, maximum_age=60, indoor=True, weather="RAIN,CLOUDY,SUNNY", address="城市青年运动馆"),
        _resource(merchants["merchant_sport"].id, target_date, name="青年运动馆体验", category="SPORT", description="篮球、羽毛球与自由运动时段组合，适合朋友和本地周末客。", start=time(14, 0), end=time(16, 0), capacity=20, settlement="70", market="128", crowds="FRIENDS,LOCAL_WEEKEND", minimum_age=12, maximum_age=60, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="城市青年运动馆"),
        _resource(merchants["merchant_food"].id, target_date, name="杭帮菜双人体验", category="FOOD", description="从一桌杭帮菜认识杭州的鲜与甜，适合情侣和本地周末客。", start=time(18, 0), end=time(20, 0), capacity=20, settlement="105", market="198", crowds="COUPLE,LOCAL_WEEKEND", minimum_age=12, maximum_age=70, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="江南味觉体验馆"),
        _resource(merchants["merchant_food"].id, target_date, name="江南甜品制作", category="FOOD", description="亲手完成桂花与江南风味甜品，适合亲子、情侣和朋友。", start=time(15, 0), end=time(16, 30), capacity=14, settlement="68", market="128", crowds="FAMILY,COUPLE,FRIENDS", minimum_age=6, maximum_age=70, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="江南味觉体验馆"),
        _resource(merchants["merchant_food"].id, target_date, name="咖啡漫游体验", category="FOOD", description="沿城市街区完成三站咖啡漫游，给独行客一个慢下来的下午。", start=time(10, 0), end=time(11, 30), capacity=2, settlement="52", market="108", crowds="SOLO,COUPLE,LOCAL_WEEKEND", minimum_age=12, maximum_age=70, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="湖滨咖啡街区"),
        _resource(merchants["merchant_nightlife"].id, target_date, name="运河夜游", category="NIGHTLIFE", description="沿运河看灯影与桥景，适合情侣和想放松的本地周末客。", start=time(19, 0), end=time(20, 30), capacity=16, settlement="98", market="178", crowds="COUPLE,LOCAL_WEEKEND", minimum_age=12, maximum_age=70, indoor=False, weather="SUNNY,CLOUDY", address="运河夜游码头"),
        _resource(merchants["merchant_nightlife"].id, target_date, name="西湖夜景漫游", category="NIGHTLIFE", description="以短距离湖畔步行为主的夜景路线，适合情侣与朋友。", start=time(18, 0), end=time(19, 30), capacity=20, settlement="45", market="98", crowds="COUPLE,FRIENDS", minimum_age=12, maximum_age=70, indoor=False, weather="SUNNY,CLOUDY", address="西湖音乐喷泉附近"),
        _resource(merchants["merchant_nightlife"].id, target_date, name="音乐现场小剧场", category="ENTERTAINMENT", description="小型音乐现场与城市夜宵路线组合，适合朋友和年轻情侣。", start=time(20, 0), end=time(22, 0), capacity=18, settlement="118", market="218", crowds="COUPLE,FRIENDS,LOCAL_WEEKEND", minimum_age=18, maximum_age=70, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="湖滨小剧场"),
        _resource(merchants["merchant_nightlife"].id, target_date, name="双人陶艺体验", category="ENTERTAINMENT", description="在夜间工作室做一对属于自己的杯子，适合情侣和朋友。", start=time(16, 0), end=time(18, 0), capacity=12, settlement="85", market="158", crowds="COUPLE,FRIENDS", minimum_age=12, maximum_age=70, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="南山陶艺空间"),
        _resource(merchants["merchant_performance"].id, target_date, name="沉浸式城市演出", category="PERFORMANCE", description="用一场沉浸式演出认识杭州的城市故事，含固定场次和实时余量。", start=time(19, 0), end=time(20, 30), capacity=20, settlement="130", market="238", crowds="COUPLE,FRIENDS,LOCAL_WEEKEND", minimum_age=12, maximum_age=70, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="城市演艺空间"),
        _resource(merchants["merchant_performance"].id, target_date, name="儿童剧周末场", category="PERFORMANCE", description="面向家庭的儿童剧场次，适合亲子完成一晚轻松的文化娱乐。", start=time(14, 0), end=time(15, 30), capacity=18, settlement="80", market="148", crowds="FAMILY", minimum_age=4, maximum_age=14, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="杭州儿童剧场"),
        _resource(merchants["merchant_performance"].id, target_date, name="宋韵演出", category="PERFORMANCE", description="以宋韵音乐与舞台叙事串起杭州夜晚，适合情侣和本地周末客。", start=time(19, 0), end=time(20, 0), capacity=16, settlement="98", market="188", crowds="COUPLE,LOCAL_WEEKEND", minimum_age=12, maximum_age=70, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="城市演艺空间"),
        _resource(merchants["merchant_reference"].id, target_date, name="杭州乐园公开信息", category="THEME_PARK", description="公开资料参考，不代表可售合作名额，不能进入正式套餐。", start=time(10, 0), end=time(10, 30), capacity=0, settlement="0", market="0", crowds="ALL", minimum_age=None, maximum_age=None, indoor=False, weather="SUNNY,CLOUDY", address="公开信息页", source_type="PUBLIC_REFERENCE", package_enabled=False),
        _resource(merchants["merchant_reference"].id, target_date, name="西湖博物馆公开导览", category="CITY_WALK", description="游客自由探索参考，不参与酒店套餐库存和收入计算。", start=time(10, 0), end=time(11, 0), capacity=0, settlement="0", market="0", crowds="FAMILY,COUPLE,SOLO", minimum_age=None, maximum_age=None, indoor=True, weather="RAIN,SUNNY,CLOUDY", address="西湖博物馆", source_type="PUBLIC_REFERENCE", package_enabled=False),
    ]
    db.add_all(resource_rows)
    db.flush()
    return {"rooms": 9, "services": 24, "merchants": len(merchants), "partner_resources": 30}
