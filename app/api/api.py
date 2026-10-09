from fastapi import APIRouter

from app.api.v1.endpoints import orders, schedules
# Импортируйте остальные роутеры по аналогии:
# from app.api.v1.endpoints import auth, photographers, studios, reviews

api_router = APIRouter()

api_router.include_router(orders.router)
api_router.include_router(schedules.router)
# api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
# api_router.include_router(photographers.router, prefix="/photographers", tags=["Photographers"])
# api_router.include_router(studios.router, prefix="/studios", tags=["Studios"])