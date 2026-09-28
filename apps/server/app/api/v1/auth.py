import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.exceptions import AppError
from ...core.security import create_access_token, verify_password
from ...db import get_db
from ...models import User
from ...schemas.auth import LoginRequest, LoginResponse, UserRead
from ..deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

_LOGIN_WINDOW_SECONDS = 300
_LOGIN_MAX_FAILURES = 5
_login_failures: dict[str, deque[float]] = defaultdict(deque)


def _login_key(request: Request, username: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}:{username.strip().lower()}"


def _login_limited(key: str) -> bool:
    now = time.monotonic()
    attempts = _login_failures[key]
    while attempts and now - attempts[0] > _LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= _LOGIN_MAX_FAILURES


def _record_login_failure(key: str) -> None:
    _login_failures[key].append(time.monotonic())


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, http_request: Request, db: Session = Depends(get_db)):
    key = _login_key(http_request, request.username)
    if _login_limited(key):
        raise AppError("AUTH_RATE_LIMITED", "登录尝试过多，请稍后再试", status_code=429, retryable=True)
    user = db.scalar(select(User).where(User.username == request.username))
    if not user or not verify_password(request.password, user.password_hash) or user.status != "ACTIVE":
        _record_login_failure(key)
        raise AppError("AUTH_INVALID", "用户名或密码错误", status_code=401)
    _login_failures.pop(key, None)
    token = create_access_token(user.username, user.role, user.id)
    return LoginResponse(access_token=token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return UserRead.model_validate(user)
