from fastapi import APIRouter

from . import auth, demo, hotel, merchant, visitor

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(demo.router)
api_router.include_router(hotel.router)
api_router.include_router(merchant.router)
api_router.include_router(visitor.router)

