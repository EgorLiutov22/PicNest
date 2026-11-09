"""
Публичный каталог: студии, залы, фотографы, услуги и доступность.

Чтение не требует авторизации: это витрина. Записывать сюда нечего —
всё управление каталогом идёт через модуль расписания и профили.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.rate_limiter import limiter
from app.schemas.catalog.schemas import (
    AvailabilityResponse,
    PhotographerDetail,
    PhotographersListResponse,
    StudioDetail,
    StudiosListResponse,
)
from app.services.catalog import CatalogService

router = APIRouter(tags=["Catalog"])


@limiter.limit("120/minute")
@router.get(
    "/studios",
    response_model=StudiosListResponse,
    summary="Список студий",
    description="Студии с количеством залов и минимальной ценой за час.",
)
async def list_studios(
    request: Request,
    search: Optional[str] = Query(None, max_length=100, description="Поиск по названию"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await CatalogService.list_studios(
        db, skip=skip, limit=limit, search=search
    )
    return StudiosListResponse(items=items, total=total, skip=skip, limit=limit)


@limiter.limit("120/minute")
@router.get(
    "/studios/{studio_id}",
    response_model=StudioDetail,
    summary="Студия с залами",
)
async def get_studio(
    request: Request,
    studio_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService.get_studio(db, studio_id)


@limiter.limit("120/minute")
@router.get(
    "/photographers",
    response_model=PhotographersListResponse,
    summary="Список фотографов",
    description="Фотографы с количеством услуг и минимальной ценой.",
)
async def list_photographers(
    request: Request,
    search: Optional[str] = Query(None, max_length=100, description="Поиск по имени"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await CatalogService.list_photographers(
        db, skip=skip, limit=limit, search=search
    )
    return PhotographersListResponse(items=items, total=total, skip=skip, limit=limit)


@limiter.limit("120/minute")
@router.get(
    "/photographers/{photographer_id}",
    response_model=PhotographerDetail,
    summary="Фотограф с услугами",
)
async def get_photographer(
    request: Request,
    photographer_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService.get_photographer(db, photographer_id)


@limiter.limit("120/minute")
@router.get(
    "/availability/{resource_type}/{resource_id}",
    response_model=AvailabilityResponse,
    summary="Занятость и свободные окна ресурса",
    description="""
    Возвращает занятые интервалы и свободные рабочие окна.

    Свободные окна уже посчитаны как рабочие часы по шаблону минус
    занятость, поэтому клиенту не нужно повторять эту арифметику.

    `resource_type`: `studio_room` или `photographer`.
    Время в ответе — UTC, рабочие часы трактуются в часовом поясе `tz`.
    """,
)
async def get_availability(
    request: Request,
    resource_type: str,
    resource_id: int,
    date_from: date = Query(..., description="Начало диапазона"),
    date_to: Optional[date] = Query(None, description="Конец диапазона"),
    tz: Optional[str] = Query(None, max_length=64, description="Часовой пояс, например Europe/Moscow"),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService.get_availability(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        date_from=date_from,
        date_to=date_to or date_from,
        user_timezone=tz,
    )
