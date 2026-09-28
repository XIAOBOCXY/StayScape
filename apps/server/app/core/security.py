import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from ..config import settings


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 240_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, role: str, user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "role": role, "user_id": user_id, "exp": expires}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])


def create_websocket_ticket(*, user_id: int, hotel_id: int) -> str:
    """Issue a short-lived ticket for a browser WebSocket handshake.

    Browsers cannot attach an Authorization header to WebSocket construction.
    The ticket is deliberately scoped to one hotel and expires in one minute,
    so access logs cannot replay the user's long-lived access JWT.
    """
    expires = datetime.now(timezone.utc) + timedelta(seconds=60)
    payload: dict[str, Any] = {
        "typ": "hotel_ws",
        "user_id": user_id,
        "hotel_id": hotel_id,
        "jti": secrets.token_urlsafe(18),
        "exp": expires,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_websocket_ticket(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    if payload.get("typ") != "hotel_ws":
        raise jwt.InvalidTokenError("invalid websocket ticket type")
    return payload
