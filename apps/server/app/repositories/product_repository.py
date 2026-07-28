from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import ProductResource, TravelProduct


def get_product(db: Session, product_id: int) -> TravelProduct | None:
    return db.scalar(select(TravelProduct).options(selectinload(TravelProduct.resources), selectinload(TravelProduct.adjustments)).where(TravelProduct.id == product_id))


def list_products(db: Session, hotel_id: int | None = None, public_only: bool = False) -> list[TravelProduct]:
    query = select(TravelProduct).options(selectinload(TravelProduct.resources), selectinload(TravelProduct.adjustments)).order_by(TravelProduct.updated_at.desc())
    if hotel_id is not None:
        query = query.where(TravelProduct.hotel_id == hotel_id)
    if public_only:
        query = query.where(TravelProduct.status.in_(["ON_SALE", "LOW_STOCK"]))
    return list(db.scalars(query).unique().all())


def products_referencing(db: Session, resource_type: str, resource_id: int) -> list[TravelProduct]:
    query = (
        select(TravelProduct)
        .join(ProductResource, ProductResource.product_id == TravelProduct.id)
        .options(selectinload(TravelProduct.resources), selectinload(TravelProduct.adjustments))
        .where(ProductResource.resource_type == resource_type, ProductResource.resource_id == resource_id)
    )
    return list(db.scalars(query).unique().all())

