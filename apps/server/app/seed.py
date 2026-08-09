from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from .core.security import hash_password
from .models import (
    Hotel,
    HotelService,
    Merchant,
    PartnerResource,
    ProductAdjustmentRecord,
    ProductResource,
    PublicResource,
    ResourceChangeEvent,
    RoomInventory,
    SkillCallLog,
    TravelProduct,
    User,
    VisitorIntent,
)


DEMO_PASSWORD = "StayScape123!"


def clear_all(db: Session) -> None:
    # Explicit order keeps this compatible with PostgreSQL foreign-key checks.
    for model in (
        VisitorIntent,
        ProductAdjustmentRecord,
        ProductResource,
        TravelProduct,
        ResourceChangeEvent,
        SkillCallLog,
        PartnerResource,
        HotelService,
        RoomInventory,
        PublicResource,
        Merchant,
        User,
        Hotel,
    ):
        db.query(model).delete(synchronize_session=False)


def seed_demo(db: Session, *, reset: bool = False) -> dict:
    if reset:
        clear_all(db)
        db.commit()
        # Bulk deletes bypass the identity map; clear loaded auth entities
        # before inserting demo rows with the same primary keys.
        db.expunge_all()
    existing = db.query(Hotel).first()
    if existing:
        target_date = db.query(RoomInventory).order_by(RoomInventory.available_date).first().available_date
        return {"hotel_id": existing.id, "target_date": target_date.isoformat(), "created": False}

    target_date = date.today() + timedelta(days=1)
    hotel = Hotel(
        name="StayScape杭州测试酒店",
        city="杭州",
        address="杭州市西湖区文旅路88号",
        contact_name="林晓",
        contact_phone="0571-88886666",
    )
    db.add(hotel)
    db.flush()

    hotel_user = User(username="hotel_demo", password_hash=hash_password(DEMO_PASSWORD), role="HOTEL", hotel_id=hotel.id)
    db.add(hotel_user)
    merchants_data = [
        ("merchant_craft", "杭州室内非遗工坊", "INTANGIBLE_CULTURE", "周老师"),
        ("merchant_tea", "西湖茶事体验馆", "TEA_CULTURE", "沈老师"),
        ("merchant_photo", "杭州亲子旅拍", "FAMILY_PHOTO", "顾老师"),
    ]
    merchant_users: dict[str, User] = {}
    for username, merchant_name, category, contact in merchants_data:
        user = User(username=username, password_hash=hash_password(DEMO_PASSWORD), role="MERCHANT")
        db.add(user)
        db.flush()
        merchant_users[username] = user
        db.add(
            Merchant(
                hotel_id=hotel.id,
                user_id=user.id,
                merchant_name=merchant_name,
                category=category,
                contact_name=contact,
                contact_phone="1380013800" + str(len(merchant_users)),
            )
        )
    db.flush()

    db.add_all(
        [
            RoomInventory(hotel_id=hotel.id, room_type="亲子房", available_date=target_date, available_count=6, normal_price=Decimal("499"), minimum_price=Decimal("399"), accounting_cost=Decimal("220"), max_guests=3, features="儿童用品、家庭空间、亲子主题", status="AVAILABLE"),
            RoomInventory(hotel_id=hotel.id, room_type="大床房", available_date=target_date, available_count=4, normal_price=Decimal("459"), minimum_price=Decimal("359"), accounting_cost=Decimal("210"), max_guests=2, features="安静采光、城市景观", status="AVAILABLE"),
            RoomInventory(hotel_id=hotel.id, room_type="双床房", available_date=target_date, available_count=3, normal_price=Decimal("479"), minimum_price=Decimal("379"), accounting_cost=Decimal("215"), max_guests=2, features="双床、亲友出行", status="AVAILABLE"),
        ]
    )
    db.add_all(
        [
            HotelService(hotel_id=hotel.id, service_name="家庭早餐", service_type="BREAKFAST", available_date=target_date, available_quantity=30, unit_cost=Decimal("15"), reference_price=Decimal("38"), start_time=time(7, 0), end_time=time(10, 0), suitable_crowds="FAMILY,COUPLE", replaceable=False, status="AVAILABLE"),
            HotelService(hotel_id=hotel.id, service_name="延迟退房", service_type="LATE_CHECKOUT", available_date=target_date, available_quantity=6, unit_cost=Decimal("10"), reference_price=Decimal("60"), start_time=time(12, 0), end_time=time(14, 0), suitable_crowds="ALL", replaceable=True, status="AVAILABLE"),
            HotelService(hotel_id=hotel.id, service_name="行李寄存", service_type="LUGGAGE_STORAGE", available_date=target_date, available_quantity=20, unit_cost=Decimal("5"), reference_price=Decimal("20"), start_time=time(10, 0), end_time=time(20, 0), suitable_crowds="ALL", replaceable=True, status="AVAILABLE"),
            HotelService(hotel_id=hotel.id, service_name="停车权益", service_type="PARKING", available_date=target_date, available_quantity=10, unit_cost=Decimal("15"), reference_price=Decimal("30"), start_time=time(10, 0), end_time=time(22, 0), suitable_crowds="ALL", replaceable=True, status="AVAILABLE"),
        ]
    )
    craft = db.query(Merchant).filter(Merchant.merchant_name == "杭州室内非遗工坊").one()
    tea = db.query(Merchant).filter(Merchant.merchant_name == "西湖茶事体验馆").one()
    photo = db.query(Merchant).filter(Merchant.merchant_name == "杭州亲子旅拍").one()
    db.add_all(
        [
            PartnerResource(merchant_id=craft.id, resource_name="室内非遗手作体验", category="CULTURE", description="在室内完成一件杭州非遗手作，适合亲子共同参与。", available_date=target_date, start_time=time(16, 0), end_time=time(17, 30), remaining_capacity=12, settlement_price=Decimal("60"), market_price=Decimal("98"), suitable_crowds="FAMILY", minimum_age=5, maximum_age=70, indoor=True, weather_tags="RAIN,SUNNY,CLOUDY", address="拱宸桥非遗工坊", booking_notice="请提前10分钟到场", cancellation_rule="体验前24小时可调整", package_enabled=True, status="AVAILABLE"),
            PartnerResource(merchant_id=tea.id, resource_name="儿童茶文化课堂", category="CULTURE", description="用儿童友好的方式认识茶叶、茶器与杭州茶文化。", available_date=target_date, start_time=time(16, 0), end_time=time(17, 15), remaining_capacity=12, settlement_price=Decimal("45"), market_price=Decimal("88"), suitable_crowds="FAMILY", minimum_age=5, maximum_age=14, indoor=True, weather_tags="RAIN,SUNNY,CLOUDY", address="西湖茶事体验馆", booking_notice="儿童需由家长陪同", cancellation_rule="体验前24小时可调整", package_enabled=True, status="AVAILABLE"),
            PartnerResource(merchant_id=tea.id, resource_name="宋韵点茶体验", category="CULTURE", description="以宋韵点茶为主题的轻文化体验。", available_date=target_date, start_time=time(10, 30), end_time=time(12, 0), remaining_capacity=9, settlement_price=Decimal("55"), market_price=Decimal("108"), suitable_crowds="FAMILY,COUPLE", minimum_age=8, maximum_age=70, indoor=True, weather_tags="RAIN,SUNNY,CLOUDY", address="西湖茶事体验馆", booking_notice="建议穿着舒适服装", cancellation_rule="体验前24小时可调整", package_enabled=True, status="AVAILABLE"),
            PartnerResource(merchant_id=photo.id, resource_name="运河亲子旅拍", category="PHOTO", description="沿运河完成一组亲子纪念照片。", available_date=target_date, start_time=time(15, 30), end_time=time(17, 0), remaining_capacity=10, settlement_price=Decimal("90"), market_price=Decimal("150"), suitable_crowds="FAMILY", minimum_age=3, maximum_age=70, indoor=False, weather_tags="SUNNY,CLOUDY", address="京杭大运河沿线", booking_notice="雨天不建议使用", cancellation_rule="天气原因可改期", package_enabled=False, status="AVAILABLE"),
        ]
    )
    db.add(
        PublicResource(resource_name="西湖博物馆", category="MUSEUM", description="可用于游客免费推荐，不参与正式套餐库存和收入计算。", address="西湖区孤山路", opening_hours="09:00-17:00", suitable_crowds="FAMILY,COUPLE", weather_tags="RAIN,SUNNY,CLOUDY", source="杭州市文化广电旅游局", verified_at=datetime.now(timezone.utc), status="ACTIVE")
    )
    db.commit()
    return {"hotel_id": hotel.id, "target_date": target_date.isoformat(), "created": True}
