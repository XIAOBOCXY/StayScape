"""The editor, the generator and the publish gate must share one rule source.

``ProductRefiner._price_floor`` and ``ProductRefiner._max_sets`` used to be
independent re-implementations of ``pricing_rule`` / ``capacity_rule``, and
``publish_check`` was a third copy.  These tests pin the unified behaviour.
"""

from decimal import Decimal, ROUND_CEILING

from app import db as db_module
from app.models import RoomInventory, TravelProduct
from app.services.product_refine_service import ProductRefiner
from app.services.product_rules_service import ProductRulesService
from tests.test_api_flow import auth, generate_request


def _generate_product_id(client, hotel_token) -> int:
    request, _ = generate_request(client, hotel_token)
    response = client.post("/api/v1/hotel/products/generate", headers=auth(hotel_token), json=request)
    assert response.status_code == 200, response.text
    return int(response.json()["product"]["id"])


def _expected_floor(product: TravelProduct, room: RoomInventory) -> Decimal:
    cost = Decimal(str(product.unit_cost or 0))
    margin = Decimal(str(product.minimum_gross_margin_requirement or "0.2"))
    return max(Decimal(str(room.minimum_price or 0)), cost / (Decimal("1") - margin)).quantize(
        Decimal("0.01"), rounding=ROUND_CEILING
    )


def test_editor_floor_matches_the_canonical_generation_floor(client, hotel_token):
    product_id = _generate_product_id(client, hotel_token)
    db = db_module.SessionLocal()
    try:
        product = db.get(TravelProduct, product_id)
        room = db.get(RoomInventory, product.room_inventory_id)
        rules = ProductRulesService(db, product.hotel_id)
        refiner = ProductRefiner(db, product.hotel_id)
        expected = _expected_floor(product, room)

        assert rules.price_floor(product) == expected
        assert refiner._price_floor(product) == expected
        # The floor stored when the product was generated is the same number.
        assert Decimal(str(product.minimum_allowed_price)) == expected
    finally:
        db.close()


def test_editor_capacity_matches_canonical_capacity(client, hotel_token):
    product_id = _generate_product_id(client, hotel_token)
    db = db_module.SessionLocal()
    try:
        product = db.get(TravelProduct, product_id)
        rules = ProductRulesService(db, product.hotel_id)
        refiner = ProductRefiner(db, product.hotel_id)

        assert refiner._max_sets(product) == rules.sale_quantity(product).sale_quantity
    finally:
        db.close()


def test_publish_check_reports_the_canonical_sellable_quantity(client, hotel_token):
    product_id = _generate_product_id(client, hotel_token)
    db = db_module.SessionLocal()
    try:
        product = db.get(TravelProduct, product_id)
        rules = ProductRulesService(db, product.hotel_id)
        refiner = ProductRefiner(db, product.hotel_id)

        check = refiner.publish_check(product)
        assert check["max_sellable"] == rules.sale_quantity(product, require_available=True).sale_quantity
        assert check["adjusted_quantity"] == min(int(product.sale_quantity or 0), check["max_sellable"])
    finally:
        db.close()


def test_unresolvable_product_reports_zero_instead_of_raising(client, hotel_token):
    product_id = _generate_product_id(client, hotel_token)
    db = db_module.SessionLocal()
    try:
        product = db.get(TravelProduct, product_id)
        rules = ProductRulesService(db, product.hotel_id)
        product.room_inventory_id = -1
        for row in list(product.resources):
            product.resources.remove(row)

        assert rules.sale_quantity(product, require_available=True).sale_quantity == 0
        assert rules.capacity_breakdown(product, require_available=True)[0].capacity == 0
    finally:
        db.close()
