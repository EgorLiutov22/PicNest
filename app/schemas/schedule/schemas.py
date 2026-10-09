"""
Pydantic v2 схемы для модуля управления расписанием PicNest.

Этот модуль содержит все схемы валидации данных для API endpoints, связанных с управлением
рабочим графиком фотографов и залов фотостудий. Включает схемы для:
- Weekly schedule templates (недельные шаблоны)
- Schedule exceptions (исключения из расписания)
- Schedule blocks (блокировки временных слотов)

Все схемы используют Pydantic v2 с strict validation и типизацией.
"""

from datetime import date, time
from enum import Enum
from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator, ConfigDict


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


# ============================================================================
# Base schemas
# ============================================================================

class ScheduleBaseModel(BaseModel):
    """Базовая схема с общими настройками валидации."""
    model_config = ConfigDict(
        strict=True,
        populate_by_name=True,
        from_attributes=True,
        use_enum_values=True,
    )


# ============================================================================
# Schedule Template schemas (недельные шаблоны)
# ============================================================================

class ScheduleTemplateBase(ScheduleBaseModel):
    """Базовая схема для шаблона расписания с общей валидацией времени."""
    
    day_of_week: DayOfWeek = Field(
        ..., 
        description="День недели (1-7, где 1 - понедельник)",
        ge=1,
        le=7
    )
    start_time: time = Field(
        ..., 
        description="Время начала работы",
        examples=["09:00:00"]
    )
    end_time: time = Field(
        ..., 
        description="Время окончания работы",
        examples=["18:00:00"]
    )

    @field_validator('end_time')
    @classmethod
    def validate_end_time_after_start(cls, v: time, info) -> time:
        """Проверяет, что время окончания строго больше времени начала."""
        if info.data.get('start_time') and v <= info.data['start_time']:
            raise ValueError('Время окончания должно быть строго после времени начала')
        return v


class ScheduleTemplateCreate(ScheduleTemplateBase):
    """Схема для создания нового шаблона расписания."""
    
    owner_id: int = Field(
        ..., 
        description="ID владельца (photographer_profile.id или room.id)",
        gt=0
    )
    owner_type: ScheduleOwnerType = Field(
        ..., 
        description="Тип владельца",
        examples=["photographer", "room"]
    )

    @field_validator('owner_id')
    @classmethod
    def validate_owner_id(cls, v: int, info) -> int:
        """Проверяет корректность owner_id в зависимости от owner_type."""
        if info.data.get('owner_type') == 'photographer' and v <= 0:
            raise ValueError('ID фотографа должен быть положительным числом')
        elif info.data.get('owner_type') == 'room' and v <= 0:
            raise ValueError('ID зала должен быть положительным числом')
        return v


class ScheduleTemplateUpdate(ScheduleBaseModel):
    """Схема для обновления существующего шаблона расписания."""
    
    day_of_week: Optional[DayOfWeek] = Field(
        None, 
        description="День недели (1-7)",
        ge=1,
        le=7
    )
    start_time: Optional[time] = Field(None, description="Время начала работы")
    end_time: Optional[time] = Field(None, description="Время окончания работы")

    @field_validator('end_time')
    @classmethod
    def validate_end_time_after_start_update(cls, v: Optional[time], info) -> Optional[time]:
        """Проверяет, что время окончания строго больше времени начала при обновлении."""
        if v is not None and info.data.get('start_time') and v <= info.data['start_time']:
            raise ValueError('Время окончания должно быть строго после времени начала')
        return v


class ScheduleTemplateResponse(ScheduleBaseModel):
    """Схема ответа с данными шаблона расписания."""
    
    id: int = Field(..., description="Уникальный ID шаблона")
    owner_id: int = Field(..., description="ID владельца")
    owner_type: str = Field(..., description="Тип владельца (photographer или room)")
    day_of_week: int = Field(..., description="День недели (1-7)")
    start_time: time = Field(..., description="Время начала работы")
    end_time: time = Field(..., description="Время окончания работы")

    class Config:
        from_attributes = True


class ScheduleTemplateListResponse(ScheduleBaseModel):
    """Схема для списка шаблонов расписания с пагинацией."""
    
    templates: List[ScheduleTemplateResponse]
    total: int = Field(..., description="Общее количество записей")
    skip: int = Field(..., description="Пропущенное количество записей")
    limit: int = Field(..., description="Лимит записей")


class ScheduleTemplatesBulkCreateRequest(ScheduleBaseModel):
    """Схема для массового создания шаблонов расписания."""
    
    templates: List[ScheduleTemplateCreate] = Field(
        ..., 
        min_length=1,
        max_length=168,  # Максимум 7 дней * 24 часа
        description="Список шаблонов для массового создания"
    )


class ScheduleTemplatesBulkResponse(ScheduleBaseModel):
    """Ответ на запрос массового создания шаблонов."""
    
    created_count: int = Field(..., description="Количество успешно созданных шаблонов")
    failed_templates: List[dict] = Field(
        default_factory=list, 
        description="Список шаблонов с ошибками валидации"
    )


# ============================================================================
# Schedule Exception schemas (исключения из расписания)
# ============================================================================

class ScheduleExceptionBase(ScheduleBaseModel):
    """Базовая схема для исключения из расписания."""
    
    date: date = Field(
        ..., 
        description="Дата исключения",
        examples=["2024-12-31"]
    )


class ScheduleExceptionCreate(ScheduleExceptionBase):
    """Схема для создания нового исключения из расписания."""
    
    owner_id: int = Field(..., description="ID владельца", gt=0)
    owner_type: ScheduleOwnerType = Field(..., description="Тип владельца")
    is_day_off: bool = Field(
        False, 
        description="Является ли день выходным (True = полный выходной)"
    )
    custom_start_time: Optional[time] = Field(
        None, 
        description="Кастомное время начала работы (если not is_day_off)"
    )
    custom_end_time: Optional[time] = Field(
        None, 
        description="Кастомное время окончания работы (если not is_day_off)"
    )

    @field_validator('custom_start_time', 'custom_end_time')
    @classmethod
    def validate_custom_times(cls, v: Optional[time], info) -> Optional[time]:
        """Проверяет логику кастомных времен при создании исключения."""
        if info.data.get('is_day_off'):
            return None  # При выходном дне кастомное время не требуется
        
        if not v and not info.data.get('custom_end_time'):
            raise ValueError(
                'При is_day_off=False необходимо указать custom_start_time и custom_end_time'
            )
        
        if v and info.data.get('custom_end_time') and v >= info.data['custom_end_time']:
            raise ValueError(
                'Время начала работы должно быть строго меньше времени окончания'
            )
        
        return v

    @field_validator('owner_id')
    @classmethod
    def validate_owner_id(cls, v: int, info) -> int:
        """Проверяет корректность owner_id."""
        if v <= 0:
            raise ValueError('ID владельца должен быть положительным числом')
        return v


class ScheduleExceptionUpdate(ScheduleBaseModel):
    """Схема для обновления исключения из расписания."""
    
    is_day_off: Optional[bool] = None
    custom_start_time: Optional[time] = Field(None, description="Кастомное время начала")
    custom_end_time: Optional[time] = Field(None, description="Кастомное время окончания")

    @field_validator('custom_start_time', 'custom_end_time')
    @classmethod
    def validate_custom_times_update(cls, v: Optional[time], info) -> Optional[time]:
        """Проверяет логику кастомных времен при обновлении."""
        if info.data.get('is_day_off'):
            return None
        
        if not v and not info.data.get('custom_end_time'):
            raise ValueError(
                'При is_day_off=False необходимо указать custom_start_time и custom_end_time'
            )
        
        if v and info.data.get('custom_end_time') and v >= info.data['custom_end_time']:
            raise ValueError(
                'Время начала работы должно быть строго меньше времени окончания'
            )
        
        return v


class ScheduleExceptionResponse(ScheduleBaseModel):
    """Схема ответа с данными исключения из расписания."""
    
    id: int = Field(..., description="Уникальный ID исключения")
    owner_id: int = Field(..., description="ID владельца")
    owner_type: str = Field(..., description="Тип владельца")
    date: date = Field(..., description="Дата исключения")
    is_day_off: bool = Field(..., description="Является ли день выходным")
    custom_start_time: Optional[time] = Field(None, description="Кастомное время начала")
    custom_end_time: Optional[time] = Field(None, description="Кастомное время окончания")

    class Config:
        from_attributes = True


class ScheduleExceptionListResponse(ScheduleBaseModel):
    """Схема для списка исключений из расписания с пагинацией."""
    
    exceptions: List[ScheduleExceptionResponse]
    total: int = Field(..., description="Общее количество записей")
    skip: int = Field(..., description="Пропущенное количество записей")
    limit: int = Field(..., description="Лимит записей")


# ============================================================================
# Schedule Block schemas (блокировки временных слотов)
# ============================================================================

class ScheduleBlockBase(ScheduleBaseModel):
    """Базовая схема для блокировки временного слота."""
    
    start_datetime: date = Field(
        ..., 
        description="Дата начала блокировки",
        examples=["2024-12-25"]
    )
    end_datetime: date = Field(
        ..., 
        description="Дата окончания блокировки",
        examples=["2024-12-26"]
    )

    @field_validator('end_datetime')
    @classmethod
    def validate_end_after_start(cls, v: date, info) -> date:
        """Проверяет, что дата окончания строго после даты начала."""
        if v <= info.data.get('start_datetime'):
            raise ValueError('Дата окончания должна быть строго после даты начала')
        return v


class ScheduleBlockCreate(ScheduleBaseModel):
    """Схема для создания новой блокировки слота."""
    
    owner_id: int = Field(..., description="ID владельца", gt=0)
    owner_type: ScheduleOwnerType = Field(..., description="Тип владельца")
    start_datetime: date = Field(
        ..., 
        description="Дата начала блокировки",
        examples=["2024-12-25"]
    )
    end_datetime: date = Field(
        ..., 
        description="Дата окончания блокировки",
        examples=["2024-12-26"]
    )

    reason: Optional[str] = Field(
        None, 
        max_length=500,
        description="Причина блокировки (опционально)"
    )


class ScheduleBlockResponse(ScheduleBaseModel):
    """Схема ответа с данными блокировки слота."""
    
    id: int = Field(..., description="Уникальный ID блокировки")
    owner_id: int = Field(..., description="ID владельца")
    owner_type: str = Field(..., description="Тип владельца")
    start_datetime: date = Field(..., description="Дата начала блокировки")
    end_datetime: date = Field(..., description="Дата окончания блокировки")
    reason: Optional[str] = Field(None, description="Причина блокировки")

    class Config:
        from_attributes = True


class ScheduleBlockListResponse(ScheduleBaseModel):
    """Схема для списка блокировок слотов с пагинацией."""
    
    blocks: List[ScheduleBlockResponse]
    total: int = Field(..., description="Общее количество записей")
    skip: int = Field(..., description="Пропущенное количество записей")
    limit: int = Field(..., description="Лимит записей")


# ============================================================================
# Query parameter schemas
# ============================================================================

class ScheduleQueryParams(ScheduleBaseModel):
    """Схема для query параметров при запросе расписания."""
    
    owner_id: Optional[int] = Field(None, description="Фильтр по ID владельца")
    owner_type: Optional[ScheduleOwnerType] = Field(
        None, 
        description="Фильтр по типу владельца"
    )
    day_of_week: Optional[DayOfWeek] = Field(
        None, 
        description="Фильтр по дню недели (для шаблонов)"
    )
    date_from: Optional[date] = Field(None, description="Дата начала фильтрации")
    date_to: Optional[date] = Field(None, description="Дата конца фильтрации")


class PaginationParams(ScheduleBaseModel):
    """Схема для пагинационных параметров."""
    
    skip: int = Field(0, ge=0, description="Пропустить N записей")
    limit: int = Field(100, ge=1, le=1000, description="Максимум записей")
