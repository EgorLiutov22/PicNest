"""
Pydantic-схемы модуля расписания PicNest.

Имена полей совпадают с тем, что уже ждут роутер и БД:
- блокировки хранят интервал во времени (start_at/end_at), а не дату:
  заблокировать «с 14 до 16» иначе невыразимо;
- списки отдают настроенные списки ключей, а не голые массивы.
"""

from datetime import date as DateType, datetime, time
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict, model_validator


class DayOfWeek(int, Enum):
    """Дни недели по ISO 8601 (понедельник = 1, воскресенье = 7)."""
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7


class ScheduleOwnerType(str, Enum):
    """Тип владельца расписания: фотограф или зал студии."""
    PHOTOGRAPHER = "photographer"
    ROOM = "room"


class ScheduleBaseModel(BaseModel):
    """Базовая схема с общими настройками.

    strict=True здесь не годится: ISO-строки дат и времени из JSON
    перестают приниматься, и клиент получает 422 на обычном запросе.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


# ============================================================================
# Templates: недельный шаблон рабочего времени
# ============================================================================

class ScheduleTemplateBase(ScheduleBaseModel):
    day_of_week: DayOfWeek = Field(
        ..., description="День недели (1-7, где 1 — понедельник)"
    )
    start_time: time = Field(..., description="Время начала работы", examples=["09:00:00"])
    end_time: time = Field(..., description="Время окончания работы", examples=["18:00:00"])

    @model_validator(mode="after")
    def validate_time_range(self) -> "ScheduleTemplateBase":
        if self.end_time <= self.start_time:
            raise ValueError("Время окончания должно быть строго после времени начала")
        return self


class ScheduleTemplateCreate(ScheduleTemplateBase):
    owner_id: int = Field(..., gt=0, description="ID владельца (профиль или зал)")
    owner_type: ScheduleOwnerType = Field(..., description="Тип владельца")


class ScheduleTemplateUpdate(ScheduleBaseModel):
    day_of_week: Optional[DayOfWeek] = Field(None, description="День недели (1-7)")
    start_time: Optional[time] = Field(None, description="Время начала работы")
    end_time: Optional[time] = Field(None, description="Время окончания работы")


class ScheduleTemplateResponse(ScheduleBaseModel):
    id: int
    owner_id: int
    owner_type: str
    day_of_week: int
    start_time: time
    end_time: time


class ScheduleTemplatesListResponse(ScheduleBaseModel):
    """Список шаблонов.

    Ключ templates, а не items: этот тип уже указан в response_model
    роутера, и переименование тихо сломало бы контракт.
    """
    templates: List[ScheduleTemplateResponse]
    total: int
    skip: int
    limit: int


class ScheduleTemplatesBulkCreateRequest(ScheduleBaseModel):
    templates: List[ScheduleTemplateCreate] = Field(
        ..., min_length=1, max_length=168,
        description="Шаблоны для массового создания (до 7 дней × 24 интервала)",
    )


class ScheduleTemplatesBulkResponse(ScheduleBaseModel):
    created_count: int
    failed_templates: List[dict] = Field(default_factory=list)


# ============================================================================
# Exceptions: выходные и изменённые часы работы
# ============================================================================

class ScheduleExceptionCreate(ScheduleBaseModel):
    owner_id: int = Field(..., gt=0, description="ID владельца")
    owner_type: ScheduleOwnerType = Field(..., description="Тип владельца")
    date: DateType = Field(..., description="Дата исключения")
    is_day_off: bool = Field(False, description="Полный выходной")
    custom_start_time: Optional[time] = Field(None, description="Время начала работы")
    custom_end_time: Optional[time] = Field(None, description="Время окончания работы")

    @model_validator(mode="after")
    def validate_hours(self) -> "ScheduleExceptionCreate":
        if self.is_day_off:
            return self

        if self.custom_start_time is None or self.custom_end_time is None:
            raise ValueError(
                "При is_day_off=False нужно указать custom_start_time и custom_end_time"
            )
        if self.custom_end_time <= self.custom_start_time:
            raise ValueError("Время окончания должно быть позже времени начала")
        return self


class ScheduleExceptionUpdate(ScheduleBaseModel):
    is_day_off: Optional[bool] = None
    custom_start_time: Optional[time] = None
    custom_end_time: Optional[time] = None

    @model_validator(mode="after")
    def validate_hours(self) -> "ScheduleExceptionUpdate":
        # Проверка частичная: остальные поля могут лежать в БД, поэтому
        # сверяем только то, что пришло в запросе.
        if self.is_day_off:
            return self
        if self.custom_start_time and self.custom_end_time:
            if self.custom_end_time <= self.custom_start_time:
                raise ValueError("Время окончания должно быть позже времени начала")
        return self


class ScheduleExceptionResponse(ScheduleBaseModel):
    id: int
    owner_id: int
    owner_type: str
    date: DateType
    is_day_off: bool
    custom_start_time: Optional[time] = None
    custom_end_time: Optional[time] = None


class ScheduleExceptionListResponse(ScheduleBaseModel):
    exceptions: List[ScheduleExceptionResponse]
    total: int
    skip: int
    limit: int


# ============================================================================
# Blocks: ручная блокировка интервала
# ============================================================================

class ScheduleBlockCreate(ScheduleBaseModel):
    owner_id: int = Field(..., gt=0, description="ID владельца")
    owner_type: ScheduleOwnerType = Field(..., description="Тип владельца")
    start_at: datetime = Field(..., description="Начало блокировки (с часовым поясом)")
    end_at: datetime = Field(..., description="Конец блокировки (с часовым поясом)")
    reason: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_range(self) -> "ScheduleBlockCreate":
        if self.end_at <= self.start_at:
            raise ValueError("Конец блокировки должен быть позже начала")
        return self


class ScheduleBlockResponse(ScheduleBaseModel):
    id: int
    owner_id: int
    owner_type: str
    start_at: datetime
    end_at: datetime
    reason: Optional[str] = None


class ScheduleBlockListResponse(ScheduleBaseModel):
    blocks: List[ScheduleBlockResponse]
    total: int
    skip: int
    limit: int


# ============================================================================
# Общие параметры запроса
# ============================================================================

class ScheduleQueryParams(ScheduleBaseModel):
    owner_id: Optional[int] = None
    owner_type: Optional[ScheduleOwnerType] = None
    day_of_week: Optional[DayOfWeek] = None
    date_from: Optional[DateType] = None
    date_to: Optional[DateType] = None


class PaginationParams(ScheduleBaseModel):
    skip: int = Field(0, ge=0, description="Пропустить N записей")
    limit: int = Field(100, ge=1, le=1000, description="Максимум записей")
