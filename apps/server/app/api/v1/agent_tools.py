"""Authenticated, narrow business tools exposed to the OpenClaw plugin.

The Feishu channel reaches the same ``stayscape-main`` Agent, but it does not
inherit the browser's FastAPI context.  These endpoints are the only bridge
from the plugin back to StayScape business data.  They deliberately expose no
SQL, shell, arbitrary HTTP, inventory mutation, price mutation, or publishing
operation.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...agent import AgentOrchestrator
from ...agent.context import RequestContext
from ...config import settings
from ...core.exceptions import AppError
from ...db import get_db
from ...models import Hotel, HotelService, Merchant, PartnerResource, RoomInventory
from ...repositories.product_repository import list_products
from ...schemas.products import GenerateProductRequest
from ...services.product_service import ProductService

router = APIRouter(prefix="/agent-tools", tags=["agent-tools"])


class ToolRequest(BaseModel):
    hotel_id: int = Field(gt=0)
    payload: dict[str, Any] = Field(default_factory=dict)


def _tool_context(
    authorization: str | None = Header(default=None),
    source_channel: str | None = Header(default=None, alias="X-StayScape-Source-Channel"),
    actor_role: str | None = Header(default=None, alias="X-StayScape-Actor-Role"),
    hotel_id: str | None = Header(default=None, alias="X-StayScape-Hotel-Id"),
    sender_id: str | None = Header(default=None, alias="X-StayScape-Sender-Id"),
    conversation_id: str | None = Header(default=None, alias="X-StayScape-Conversation-Id"),
) -> RequestContext:
    expected = settings.stayscape_agent_tool_token
    if not expected or authorization != f"Bearer {expected}":
        raise AppError("AGENT_TOOL_UNAUTHORIZED", "Agent Tool authentication failed", status_code=401)
    if source_channel != "FEISHU" or actor_role not in {"HOTEL_OPERATOR", "HOTEL_SUPPORT"} or not hotel_id:
        raise AppError("AGENT_TOOL_CONTEXT_REQUIRED", "Missing a trusted Feishu source, role, or hotel context", status_code=403)
    allowed_senders = {item.strip() for item in settings.feishu_dm_allow_from.split(",") if item.strip()}
    if not sender_id or not allowed_senders or sender_id not in allowed_senders:
        raise AppError("FEISHU_SENDER_FORBIDDEN", "The Feishu sender is not on the business tool allowlist", status_code=403)
    try:
        parsed_hotel_id = int(hotel_id)
    except (TypeError, ValueError) as exc:
        raise AppError("AGENT_TOOL_CONTEXT_INVALID", "The hotel context is invalid", status_code=403) from exc
    return RequestContext(
        source_channel="FEISHU",
        actor_role=actor_role,
        hotel_id=parsed_hotel_id,
        conversation_id=conversation_id,
    )


def _hotel_or_404(db: Session, hotel_id: int) -> Hotel:
    hotel = db.get(Hotel, hotel_id)
    if not hotel or hotel.status != "ACTIVE":
        raise AppError("HOTEL_NOT_FOUND", "The hotel does not exist or is inactive", status_code=404)
    return hotel


def _assert_hotel_context(context: RequestContext, hotel_id: int) -> None:
    if context.hotel_id != hotel_id:
        raise AppError("AGENT_TOOL_CONTEXT_INVALID", "The request hotel differs from the trusted context", status_code=403)


def _partner_resource_context(resource: PartnerResource) -> dict[str, Any]:
    """Return only the operational fields a Feishu Agent needs to plan a draft.

    Settlement and market prices stay inside FastAPI's deterministic pricing
    boundary.  The Agent can select a resource by its public operating
    attributes; it must never become the source of truth for cost or price.
    """
    return {
        "id": resource.id,
        "merchant_id": resource.merchant_id,
        "merchant_name": resource.merchant.merchant_name if resource.merchant else None,
        "resource_name": resource.resource_name,
        "category": resource.category,
        "description": resource.description,
        "available_date": resource.available_date,
        "start_time": resource.start_time,
        "end_time": resource.end_time,
        "remaining_capacity": resource.remaining_capacity,
        "suitable_crowds": resource.suitable_crowds,
        "minimum_age": resource.minimum_age,
        "maximum_age": resource.maximum_age,
        "indoor": resource.indoor,
        "weather_tags": resource.weather_tags,
        "address": resource.address,
        "booking_notice": resource.booking_notice,
        "package_enabled": resource.package_enabled,
        "source_type": resource.source_type,
        "status": resource.status,
    }


def _draft_summary(product) -> dict[str, Any]:
    """Keep Feishu's write response useful without leaking internal accounting."""
    return {
        "id": product.id,
        "product_name": product.product_name,
        "marketing_title": product.marketing_title,
        "theme": product.theme,
        "target_crowd": product.target_crowd,
        "weather": product.weather,
        "target_date": product.target_date,
        "sale_quantity": product.sale_quantity,
        "suggested_price": str(product.suggested_price),
        "status": product.status,
        "resources": [
            {
                "resource_type": item.resource_type,
                "resource_id": item.resource_id,
                "resource_name": item.resource_name,
                "quantity_per_package": item.quantity_per_package,
                "available_date": getattr(item, "available_date", None),
                "start_time": getattr(item, "start_time", None),
                "end_time": getattr(item, "end_time", None),
            }
            for item in product.resources
        ],
    }


@router.post("/hotel-context")
def hotel_context(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    _assert_hotel_context(context, request.hotel_id)
    _hotel_or_404(db, request.hotel_id)
    rooms = list(
        db.scalars(
            select(RoomInventory)
            .where(RoomInventory.hotel_id == request.hotel_id)
            .order_by(RoomInventory.available_date, RoomInventory.id)
        ).all()
    )
    services = list(
        db.scalars(
            select(HotelService)
            .where(HotelService.hotel_id == request.hotel_id)
            .order_by(HotelService.available_date, HotelService.id)
        ).all()
    )
    resources = list(
        db.scalars(
            select(PartnerResource)
            .join(Merchant)
            .where(Merchant.hotel_id == request.hotel_id)
            .order_by(PartnerResource.available_date, PartnerResource.id)
        ).all()
    )
    return {
        "hotel_id": request.hotel_id,
        "rooms": [
            {
                "id": item.id,
                "room_type": item.room_type,
                "available_date": item.available_date,
                "available_count": item.available_count,
                "max_guests": item.max_guests,
                "suitable_crowds": item.suitable_crowds,
                "tags": item.tags,
                "status": item.status,
            }
            for item in rooms
        ],
        "services": [
            {
                "id": item.id,
                "service_name": item.service_name,
                "service_type": item.service_type,
                "available_date": item.available_date,
                "available_quantity": item.available_quantity,
                "start_time": item.start_time,
                "end_time": item.end_time,
                "status": item.status,
                "suitable_crowds": item.suitable_crowds,
            }
            for item in services
        ],
        "partner_resources": [_partner_resource_context(item) for item in resources],
        "source_channel": context.source_channel,
        "actor_role": context.actor_role,
    }


@router.post("/available-products")
def available_products(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    _assert_hotel_context(context, request.hotel_id)
    _hotel_or_404(db, request.hotel_id)
    products = list_products(db, hotel_id=request.hotel_id, public_only=True)
    payload = request.payload
    target_date = payload.get("target_date")
    budget = payload.get("budget")
    if target_date:
        products = [item for item in products if item.target_date and item.target_date.isoformat() == str(target_date)]
    if budget is not None:
        try:
            budget_value = Decimal(str(budget))
            products = [item for item in products if item.suggested_price <= budget_value]
        except (InvalidOperation, TypeError, ValueError):
            raise AppError("VALIDATION_ERROR", "Budget must be a valid number", status_code=422)
    from ...api.v1.visitor import safe_product_context

    return {
        "items": [safe_product_context(db, item) for item in products],
        "source_channel": context.source_channel,
        "actor_role": context.actor_role,
    }


@router.post("/product-draft")
def create_product_draft(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    _assert_hotel_context(context, request.hotel_id)
    if context.actor_role != "HOTEL_OPERATOR":
        raise AppError("FORBIDDEN", "Only an allowlisted hotel operator can create a product draft", status_code=403)
    try:
        generate_request = GenerateProductRequest.model_validate(request.payload)
    except Exception as exc:
        raise AppError("VALIDATION_ERROR", "Product draft parameters are invalid", details=str(exc)) from exc
    orchestrator = AgentOrchestrator(db, hotel_id=request.hotel_id, context=context)
    generated = ProductService(db, request.hotel_id, orchestrator=orchestrator).generate_many(generate_request)
    db.commit()
    products = [item[0] for item in generated]
    return {
        "product_id": products[0].id,
        "product": _draft_summary(products[0]),
        "products": [_draft_summary(item) for item in products],
        "trace_ids": [item[2] for item in generated],
        "fallback_used": any(item[3] for item in generated),
        "web_url": f"/hotel/products/{products[0].id}",
    }
