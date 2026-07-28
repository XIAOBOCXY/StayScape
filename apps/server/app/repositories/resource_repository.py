from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import HotelService, Merchant, PartnerResource, RoomInventory


def list_partner_resources(db: Session, hotel_id: int) -> list[PartnerResource]:
    query = select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(Merchant.hotel_id == hotel_id).order_by(PartnerResource.available_date, PartnerResource.id)
    return list(db.scalars(query).unique().all())


def list_services(db: Session, hotel_id: int) -> list[HotelService]:
    return list(db.scalars(select(HotelService).where(HotelService.hotel_id == hotel_id).order_by(HotelService.available_date, HotelService.id)).all())


def list_rooms(db: Session, hotel_id: int) -> list[RoomInventory]:
    return list(db.scalars(select(RoomInventory).where(RoomInventory.hotel_id == hotel_id).order_by(RoomInventory.available_date, RoomInventory.id)).all())

