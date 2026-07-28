from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.exceptions import AppError
from ..core.security import decode_access_token
from ..db import get_db
from ..models import Hotel, Merchant, User

bearer = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise AppError("AUTH_REQUIRED", "请先登录", status_code=401)
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload.get("user_id"))
    except Exception as exc:
        raise AppError("AUTH_INVALID", "登录凭证无效或已过期", status_code=401) from exc
    user = db.get(User, user_id)
    if not user or user.status != "ACTIVE":
        raise AppError("AUTH_INVALID", "用户不存在或已停用", status_code=401)
    return user


def require_roles(*roles: str) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise AppError("FORBIDDEN", "当前角色无权执行此操作", status_code=403)
        return user

    return dependency


def resolve_hotel_id(db: Session, user: User) -> int:
    if user.role == "MERCHANT":
        merchant = db.scalar(select(Merchant).where(Merchant.user_id == user.id))
        if not merchant:
            raise AppError("HOTEL_NOT_FOUND", "当前商户未绑定酒店", status_code=404)
        return merchant.hotel_id
    hotel = db.scalar(select(Hotel).order_by(Hotel.id))
    if not hotel:
        raise AppError("HOTEL_NOT_FOUND", "尚未初始化演示酒店", status_code=404)
    return hotel.id


def get_hotel_user(user: User = Depends(require_roles("HOTEL"))) -> User:
    return user


def get_merchant_user(user: User = Depends(require_roles("MERCHANT"))) -> User:
    return user

