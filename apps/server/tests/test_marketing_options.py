import pytest
from pydantic import ValidationError

from app.schemas.products import MarketingRegenerationRequest
from app.services.product_service import marketing_style_direction


def test_marketing_style_request_defaults_to_seeding_without_image():
    request = MarketingRegenerationRequest()
    assert request.style == "SEEDING"
    assert request.generate_image is False


def test_marketing_style_direction_uses_public_facing_copy_guardrails():
    direction = marketing_style_direction("ARTISTIC")
    assert "文艺叙事" in direction
    assert "规则引擎" in direction


def test_marketing_request_cannot_override_server_owned_wan_model():
    with pytest.raises(ValidationError):
        MarketingRegenerationRequest(image_model="wan2.7-image-pro")
