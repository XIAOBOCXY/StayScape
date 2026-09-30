from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, defer, selectinload

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


def get_products_for_serialization(db: Session, product_ids: list[int], hotel_id: int) -> list[TravelProduct]:
    ids = list(dict.fromkeys(int(value) for value in product_ids if int(value) > 0))
    if not ids:
        return []
    query = (
        select(TravelProduct)
        .options(
            selectinload(TravelProduct.resources),
            selectinload(TravelProduct.room_inventory),
            selectinload(TravelProduct.hotel),
        )
        .where(TravelProduct.hotel_id == hotel_id, TravelProduct.id.in_(ids))
    )
    return list(db.scalars(query).unique().all())


def list_products_for_serialization(
    db: Session,
    hotel_id: int,
    *,
    status: str | None = None,
    exclude_status: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    target_date: date | None = None,
) -> list[TravelProduct]:
    """Load card-ready products without hydrating unused marketing blobs."""
    query = (
        select(TravelProduct)
        .options(
            selectinload(TravelProduct.resources),
            selectinload(TravelProduct.room_inventory),
            selectinload(TravelProduct.hotel),
            defer(TravelProduct.marketing_assets),
        )
        .where(TravelProduct.hotel_id == hotel_id, TravelProduct.status != "DELETED")
        .order_by(TravelProduct.updated_at.desc(), TravelProduct.id.desc())
    )
    if status:
        query = query.where(TravelProduct.status == status)
    if exclude_status:
        query = query.where(TravelProduct.status != exclude_status)
    if target_date is not None:
        query = query.where(TravelProduct.target_date == target_date)
    if offset:
        query = query.offset(max(0, int(offset)))
    if limit is not None:
        query = query.limit(max(1, int(limit)))
    return list(db.scalars(query).unique().all())


def list_public_products_for_serialization(
    db: Session,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[TravelProduct]:
    """Load visitor card rows without adjustments, unused assets, or the full room calendar."""
    query = (
        select(TravelProduct)
        .options(
            selectinload(TravelProduct.resources),
            selectinload(TravelProduct.room_inventory),
            selectinload(TravelProduct.hotel),
            defer(TravelProduct.marketing_assets),
        )
        .where(
            TravelProduct.status.in_(["ON_SALE", "LOW_STOCK"]),
            TravelProduct.target_date >= date.today(),
        )
        .order_by(TravelProduct.updated_at.desc(), TravelProduct.id.desc())
    )
    if offset:
        query = query.offset(max(0, int(offset)))
    if limit is not None:
        query = query.limit(max(1, int(limit)))
    return list(db.scalars(query).unique().all())


def list_products(
    db: Session,
    hotel_id: int | None = None,
    public_only: bool = False,
    *,
    limit: int | None = None,
    offset: int = 0,
    status: str | None = None,
    exclude_status: str | None = None,
    target_date: date | None = None,
) -> list[TravelProduct]:
    query = select(TravelProduct).options(*_product_options()).order_by(TravelProduct.updated_at.desc(), TravelProduct.id.desc())
    if hotel_id is not None:
        query = query.where(TravelProduct.hotel_id == hotel_id, TravelProduct.status != "DELETED")
    if status:
        query = query.where(TravelProduct.status == status)
    if exclude_status:
        query = query.where(TravelProduct.status != exclude_status)
    if target_date is not None:
        query = query.where(TravelProduct.target_date == target_date)
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
