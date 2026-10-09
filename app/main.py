from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenExpiredError,
    UserInactiveError,
    InvalidTokenPayloadError,
    UserStatusError,
)
from app.routers.auth import router as auth_router
from app.routers.orders import router as orders_router


app = FastAPI(
    title="PicNest Marketplace API",
    description="RESTful API для маркетплейса фотостудий и фотографов с управлением расписанием и заказами",
    version="1.0.0",
)

@app.on_event("startup")
async def startup():
    from app.core.db import init_db
    await init_db()


app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(orders_router, prefix="/api/v1/orders", tags=["Orders Management"])
# TODO: Подключить роутер расписания после создания модели ScheduleBlock в БД
