from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...config import settings
from ...core.exceptions import AppError
from ...db import get_db
from ...seed import seed_demo
from ..deps import get_hotel_user

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset_demo(db: Session = Depends(get_db), _user=Depends(get_hotel_user)):
    if settings.app_env.lower() == "production":
        raise AppError("FORBIDDEN", "生产环境不允许重置演示数据", status_code=403)
    result = seed_demo(db, reset=True, include_showcase=True)
    return {"message": "演示数据已重置", **result}


@router.post("/seed")
def seed(db: Session = Depends(get_db), _user=Depends(get_hotel_user)):
    if settings.app_env.lower() == "production":
        raise AppError("FORBIDDEN", "生产环境不允许写入演示数据", status_code=403)
    result = seed_demo(db, reset=False, include_showcase=True)
    return {"message": "演示数据已准备", **result}
