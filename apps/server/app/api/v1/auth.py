from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.exceptions import AppError
from ...core.security import create_access_token, verify_password
from ...db import get_db
from ...models import User
from ...schemas.auth import LoginRequest, LoginResponse, UserRead
from ..deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == request.username))
    if not user or not verify_password(request.password, user.password_hash) or user.status != "ACTIVE":
        raise AppError("AUTH_INVALID", "用户名或密码错误", status_code=401)
    token = create_access_token(user.username, user.role, user.id)
    return LoginResponse(access_token=token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return UserRead.model_validate(user)

