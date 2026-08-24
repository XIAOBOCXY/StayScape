from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .api.v1.router import api_router
from .api.websocket_manager import manager
from .config import settings
from .core.exceptions import AppError
from .core.security import decode_access_token
from .db import SessionLocal, engine
from .models import Base, User
from .seed import seed_demo
from .api.deps import resolve_hotel_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_startup:
        db = SessionLocal()
        try:
            seed_demo(db, include_showcase=True)
        finally:
            db.close()
    yield


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan, docs_url="/docs", redoc_url="/redoc")
    Path(settings.generated_media_dir).mkdir(parents=True, exist_ok=True)
    application.mount(settings.generated_media_url_path, StaticFiles(directory=settings.generated_media_dir), name="generated-media")
    application.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @application.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=exc.as_dict())

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"success": False, "error": {"code": "VALIDATION_ERROR", "message": "请求参数校验失败", "field": None, "retryable": False, "suggestion": "请检查输入内容", "details": exc.errors()}})

    @application.get("/health")
    def health():
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            database = "ok"
        except Exception:
            database = "error"
        finally:
            db.close()
        return {"status": "ok" if database == "ok" else "degraded", "app": settings.app_name, "database": database, "agent_provider": settings.agent_provider}

    application.include_router(api_router, prefix="/api/v1")

    @application.websocket("/ws/hotel/{hotel_id}")
    async def hotel_websocket(websocket: WebSocket, hotel_id: int):
        token = websocket.query_params.get("token")
        db = SessionLocal()
        try:
            if not token:
                await websocket.close(code=1008)
                return
            payload = decode_access_token(token)
            user = db.get(User, int(payload.get("user_id")))
            if not user or user.status != "ACTIVE" or user.role != "HOTEL" or resolve_hotel_id(db, user) != hotel_id:
                await websocket.close(code=1008)
                return
        except Exception:
            await websocket.close(code=1008)
            return
        finally:
            db.close()
        await manager.connect(hotel_id, websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(hotel_id, websocket)
        except Exception:
            manager.disconnect(hotel_id, websocket)

    return application


app = create_app()
