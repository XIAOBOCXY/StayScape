from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Hotel, ProductResource, TravelProduct


def _product_options():
    """Eager loading shared by the visitor and workbench reads.

    ``build_stay_plan`` needs the hotel's room graph to verify a multi-night
    stay; without it every multi-day product silently degraded to 2天1晚.
    """

    return (
        selectinload(TravelProduct.resources),
        selectinload(TravelProduct.adjustments),
        selectinload(TravelProduct.room_inventory),
        selectinload(TravelProduct.hotel).selectinload(Hotel.rooms),
    )


def get_product(db: Session, product_id: int) -> TravelProduct | None:
    return db.scalar(select(TravelProduct).options(*_product_options()).where(TravelProduct.id == product_id))


def list_products(
    db: Session,
    hotel_id: int | None = None,
    public_only: bool = False,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[TravelProduct]:
    query = select(TravelProduct).options(*_product_options()).order_by(TravelProduct.updated_at.desc())
    if hotel_id is not None:
        query = query.where(TravelProduct.hotel_id == hotel_id, TravelProduct.status != "DELETED")
    if public_only:
        query = query.where(
            TravelProduct.status.in_(["ON_SALE", "LOW_STOCK"]),
            TravelProduct.target_date >= date.today(),
        )
    if limit is not None:
        query = query.offset(max(0, offset)).limit(max(1, limit))
    return list(db.scalars(query).unique().all())


def products_referencing(db: Session, resource_type: str, resource_id: int) -> list[TravelProduct]:
    query = (
        select(TravelProduct)
        .join(ProductResource, ProductResource.product_id == TravelProduct.id)
        .options(selectinload(TravelProduct.resources), selectinload(TravelProduct.adjustments))
        .where(ProductResource.resource_type == resource_type, ProductResource.resource_id == resource_id, TravelProduct.status != "DELETED")
    )
    return list(db.scalars(query).unique().all())
