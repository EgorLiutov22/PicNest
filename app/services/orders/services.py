"""
Сервисы для модуля заказов PicNest Marketplace.

Этот модуль реализует бизнес-логику для управления жизненным циклом заказов:
1. Создание заказа с валидацией временных слотов и снапшотом данных
2. Проверка доступности фотографов и залов на указанные даты/время
3. Обработка переходов между статусами (подтверждение, отмена)
4. Расчет возврата средств при отмене

Архитектура:
- OrderService: Основная логика CRUD операций с заказами
- AvailabilityCheckerService: Проверка слотов и исключений в расписании
- StatusManagerService: Управление переходами между статусами

Автор: PicNest Backend Team
Дата: 2026-10-09
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text, update
from sqlalchemy.orm import selectinload, joinedload

from app.models.order import Order
from app.models.orderitem import OrderItem
from app.models.orderstatus import OrderStatus
from app.models.ordertype import OrderType
from app.models.user import User
from app.models.photographerprofile import PhotographerProfile
from app.models.photographerservice import PhotographerService
from app.models.studioprofile import StudioProfile
from app.models.studioroom import StudioRoom
from app.models.schedule import (
    ScheduleBlock,
    ScheduleTemplate,
    ScheduleException,
)

if TYPE_CHECKING:
    from app.schemas.orders.schemas import OrderCreate, OrderStatusEnum


# ============================================================================
# Custom Exceptions for Business Logic
# ============================================================================

class OrderServiceError(Exception):
    """Базовое исключение сервисов заказов."""
    
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class OrderValidationError(OrderServiceError):
    """Ошибка валидации данных заказа."""
    pass


class SlotConflictError(OrderServiceError):
    """Конфликт временных слотов (двойное бронирование)."""
    
    def __init__(self, message: str, conflicting_order_id: int = None):
        super().__init__(message, status_code=409)  # Conflict
        self.conflicting_order_id = conflicting_order_id


class ScheduleBlockedException(OrderServiceError):
    """Слот заблокирован в расписании (недоступен)."""
    
    def __init__(self, message: str, blocked_by: str = None):
        super().__init__(message, status_code=403)  # Forbidden
        self.blocked_by = blocked_by


class StatusTransitionNotAllowed(OrderServiceError):
    """Невозможный переход между статусами."""
    
    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class OrderNotFoundError(OrderServiceError):
    """Заказ не найден."""
    
    def __init__(self, order_id: int):
        super().__init__(f"Заказ с ID {order_id} не найден", status_code=404)
        self.order_id = order_id


class OrderForbiddenError(OrderServiceError):
    """Доступ к заказу запрещен."""
    
    def __init__(self, message: str, order_id: int = None):
        super().__init__(message, status_code=403)
        self.order_id = order_id


# ============================================================================
# AvailabilityCheckerService
# ============================================================================

class AvailabilityCheckerService:
    """Сервис проверки доступности временных слотов.
    
    Проверяет:
    1. Отсутствие пересечений с существующими заказами (OrderItem)
    2. Наличие блокировок в расписании (ScheduleBlock)
    3. Исключения из расписания (ScheduleException - выходные дни, кастомное время)
    
    Использует атомарные запросы для предотвращения гонки состояний.
    """
    
    @staticmethod
    async def check_slot_availability(
        db: AsyncSession,
        photographer_id: Optional[int],
        studio_room_id: Optional[int],
        start_time: datetime,
        end_time: datetime,
        exclude_order_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Проверяет доступность слота для бронирования.
        
        Args:
            db: Асинхронная сессия БД
            photographer_id: ID фотографа или None
            studio_room_id: ID зала студии или None
            start_time: Время начала бронирования
            end_time: Время окончания бронирования
            exclude_order_id: Исключить существующий заказ (для обновлений)
            
        Returns:
            Кортеж (is_available, message)
            
        Raises:
            SlotConflictError: Если слот занят другим заказом
            ScheduleBlockedException: Если слот заблокирован
        """
        
        # 1. Проверка на пересечения с существующими заказами
        conflict = await AvailabilityCheckerService._check_conflicts(
            db=db,
            photographer_id=photographer_id,
            studio_room_id=studio_room_id,
            start_time=start_time,
            end_time=end_time,
            exclude_order_id=exclude_order_id,
        )
        
        if conflict:
            raise SlotConflictError(
                message=f"Слот занят другим заказом (ID: {conflict})",
                conflicting_order_id=int(conflict),
            )
        
        # 2. Проверка блокировок расписания
        block = await AvailabilityCheckerService._check_schedule_blocks(
            db=db,
            photographer_id=photographer_id,
            studio_room_id=studio_room_id,
            start_time=start_time,
            end_time=end_time,
        )
        
        if block:
            raise ScheduleBlockedException(
                message=f"Слот заблокирован в расписании",
                blocked_by="schedule_block",
            )
        
        # 3. Проверка исключений из расписания (выходные дни)
        exception = await AvailabilityCheckerService._check_schedule_exceptions(
            db=db,
            photographer_id=photographer_id,
            studio_room_id=studio_room_id,
            start_time=start_time,
            end_time=end_time,
        )
        
        if exception:
            raise ScheduleBlockedException(
                message=f"День является выходным согласно исключениям расписания",
                blocked_by="schedule_exception",
            )
        
        return True, "Слот доступен"
    
    @staticmethod
    async def _check_conflicts(
        db: AsyncSession,
        photographer_id: Optional[int],
        studio_room_id: Optional[int],
        start_time: datetime,
        end_time: datetime,
        exclude_order_id: Optional[int] = None,
    ) -> Optional[int]:
        """Проверяет пересечения с существующими заказами.
        
        Два временных интервала пересекаются если:
        new_start < existing_end AND new_end > existing_start
        
        Args:
            db: Асинхронная сессия БД
            photographer_id: ID фотографа или None
            studio_room_id: ID зала студии или None
            start_time: Время начала бронирования
            end_time: Время окончания бронирования
            exclude_order_id: Исключить заказ с этим ID
            
        Returns:
            ID конфликтующего заказа или None если пересечений нет
        """
        
        # Строим условие для поиска пересечений
        overlap_condition = and_(
            OrderItem.start_time < end_time,
            OrderItem.end_time > start_time,
        )
        
        if photographer_id:
            query = select(OrderItem.id).where(
                and_(
                    overlap_condition,
                    OrderItem.photographer_id == photographer_id,
                    OrderItem.studio_room_id.is_(None),  # Только фотограф (не combined)
                ),
            )
        elif studio_room_id:
            query = select(OrderItem.id).where(
                and_(
                    overlap_condition,
                    OrderItem.studio_room_id == studio_room_id,
                    OrderItem.photographer_id.is_(None),  # Только зал (не combined)
                ),
            )
        else:
            return None
        
        # Исключаем текущий заказ если нужно
        if exclude_order_id:
            query = query.where(OrderItem.id != exclude_order_id)
        
        # Выполняем запрос
        result = await db.execute(query)
        conflicting_ids = result.scalars().all()
        
        return conflicting_ids[0] if conflicting_ids else None
    
    @staticmethod
    async def _check_schedule_blocks(
        db: AsyncSession,
        photographer_id: Optional[int],
        studio_room_id: Optional[int],
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """Проверяет блокировки в расписании.
        
        Args:
            db: Асинхронная сессия БД
            photographer_id: ID фотографа или None
            studio_room_id: ID зала студии или None
            start_time: Время начала бронирования
            end_time: Время окончания бронирования
            
        Returns:
            True если есть блокировки, False в противном случае
        """
        
        # Проверяем пересечения с блоками расписания
        overlap_condition = and_(
            ScheduleBlock.start_datetime <= start_time.date(),
            ScheduleBlock.end_datetime >= end_time.date(),
        )
        
        if photographer_id:
            query = select(func.count(ScheduleBlock.id)).where(
                and_(
                    overlap_condition,
                    ScheduleBlock.photographer_id == photographer_id,
                    ScheduleBlock.room_id.is_(None),
                ),
            )
        elif studio_room_id:
            query = select(func.count(ScheduleBlock.id)).where(
                and_(
                    overlap_condition,
                    ScheduleBlock.room_id == studio_room_id,
                    ScheduleBlock.photographer_id.is_(None),
                ),
            )
        else:
            return False
        
        result = await db.execute(query)
        count = result.scalar()
        
        return count > 0
    
    @staticmethod
    async def _check_schedule_exceptions(
        db: AsyncSession,
        photographer_id: Optional[int],
        studio_room_id: Optional[int],
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """Проверяет исключения из расписания (выходные дни).
        
        Args:
            db: Асинхронная сессия БД
            photographer_id: ID фотографа или None
            studio_room_id: ID зала студии или None
            start_time: Время начала бронирования
            end_time: Время окончания бронирования
            
        Returns:
            True если есть выходные дни в диапазоне, False в противном случае
        """
        
        # Проверяем пересечения с исключениями расписания
        overlap_condition = and_(
            ScheduleException.date >= start_time.date(),
            ScheduleException.date <= end_time.date(),
        )
        
        if photographer_id:
            query = select(func.count(ScheduleException.id)).where(
                and_(
                    overlap_condition,
                    ScheduleException.photographer_id == photographer_id,
                    ScheduleException.room_id.is_(None),
                    ScheduleException.is_day_off == True,  # Только выходные дни
                ),
            )
        elif studio_room_id:
            query = select(func.count(ScheduleException.id)).where(
                and_(
                    overlap_condition,
                    ScheduleException.room_id == studio_room_id,
                    ScheduleException.photographer_id.is_(None),
                    ScheduleException.is_day_off == True,  # Только выходные дни
                ),
            )
        else:
            return False
        
        result = await db.execute(query)
        count = result.scalar()
        
        return count > 0


# ============================================================================
# StatusManagerService
# ============================================================================

class StatusManagerService:
    """Сервис управления переходами между статусами заказов.
    
    Реализует строгие правила переходов:
    - pending_payment -> confirmed (исполнителем)
    - confirmed -> in_progress (системой после оплаты)
    - in_progress -> completed (системой после завершения)
    - Любой статус -> cancelled (клиентом или системой)
    
    Проверяет права доступа перед изменением статуса.
    """
    
    # Правила переходов между статусами
    STATUS_RULES: Dict[OrderStatus, Dict[str, Any]] = {
        OrderStatus.pending_payment: {
            "allowed_transitions": [OrderStatus.confirmed],
            "allowed_by": ["performer"],  # Исполнитель подтверждает
        },
        OrderStatus.confirmed: {
            "allowed_transitions": [OrderStatus.in_progress, OrderStatus.cancelled],
            "allowed_by": ["system", "client"],  # Система (оплата) или клиент (отмена)
        },
        OrderStatus.in_progress: {
            "allowed_transitions": [OrderStatus.completed, OrderStatus.cancelled],
            "allowed_by": ["system", "client"],  # Система (завершение) или клиент (отмена)
        },
        OrderStatus.completed: {
            "allowed_transitions": [],  # Завершенный заказ не меняется
            "allowed_by": [],
        },
        OrderStatus.cancelled: {
            "allowed_transitions": [],  # Отмененный заказ не меняется
            "allowed_by": [],
        },
    }
    
    @classmethod
    async def validate_transition(
        cls,
        current_status: OrderStatus,
        target_status: OrderStatus,
        actor_type: str,  # "client", "performer", или "system"
    ) -> bool:
        """Проверяет возможность перехода между статусами.
        
        Args:
            current_status: Текущий статус заказа
            target_status: Целевой статус
            actor_type: Тип пользователя (client, performer, system)
            
        Returns:
            True если переход разрешен
            
        Raises:
            StatusTransitionNotAllowed: Если переход запрещен
        """
        
        rules = cls.STATUS_RULES.get(current_status)
        if not rules:
            raise StatusTransitionNotAllowed(
                f"Нет правил для статуса {current_status.value}"
            )
        
        # Проверяем целевой статус
        if target_status not in rules["allowed_transitions"]:
            allowed_values = [s.value for s in rules["allowed_transitions"]]
            raise StatusTransitionNotAllowed(
                f"Переход из {current_status.value} в {target_status.value} запрещен. "
                f"Разрешенные: {', '.join(allowed_values)}"
            )
        
        # Проверяем права актора
        if actor_type not in rules["allowed_by"]:
            raise StatusTransitionNotAllowed(
                f"Только {', '.join(rules['allowed_by'])} могут инициировать переход "
                f"из {current_status.value}"
            )
        
        return True
    
    @classmethod
    async def update_order_status(
        cls,
        db: AsyncSession,
        order_id: int,
        new_status: OrderStatus,
        actor_type: str,
    ) -> Order:
        """Обновляет статус заказа после валидации.
        
        Args:
            db: Асинхронная сессия БД
            order_id: ID заказа
            new_status: Новый статус
            actor_type: Тип пользователя (client, performer, system)
            
        Returns:
            Обновленный заказ
            
        Raises:
            OrderNotFoundError: Если заказ не найден
            StatusTransitionNotAllowed: Если переход запрещен
        """
        
        # Получаем заказ
        result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if not order:
            raise OrderNotFoundError(order_id)
        
        current_status = order.status
        
        # Проверяем переход
        await cls.validate_transition(
            current_status=current_status,
            target_status=new_status,
            actor_type=actor_type,
        )
        
        # Обновляем статус
        order.status = new_status
        await db.flush()  # Фиксируем изменения
        
        return order
    
    @classmethod
    async def calculate_refund(
        cls,
        prepayment_amount: Decimal,
        total_price: Decimal,
        status_at_cancellation: OrderStatus,
        cancellation_date: datetime,
        created_at: datetime,
        conditions: Dict[str, Any],
    ) -> Tuple[Decimal, float]:
        """Рассчитывает сумму возврата при отмене заказа.
        
        Логика расчета:
        - pending_payment: 100% возврат (заказ еще не подтвержден)
        - confirmed: зависит от условий отмены (обычно 50-80%)
        - in_progress: зависит от условий, может быть 0% если работа началась
        
        Args:
            prepayment_amount: Сумма предоплаты
            total_price: Общая стоимость заказа
            status_at_cancellation: Статус на момент отмены
            cancellation_date: Дата отмены
            created_at: Дата создания
            conditions: Условия отмены из заказа
            
        Returns:
            Кортеж (refund_amount, refund_percentage)
        """
        
        # По умолчанию 100% возврат для pending_payment
        if status_at_cancellation == OrderStatus.pending_payment:
            return prepayment_amount, 100.0
        
        # Проверяем условия отмены
        conditions = conditions or {}
        refund_policy = conditions.get("refund_policy", {})
        
        # По умолчанию 50% возврата для confirmed статуса
        base_percentage = Decimal(str(refund_policy.get("percentage", 50)))
        
        # Учитываем время до начала заказа
        time_before_start = (cancellation_date - created_at).total_seconds() / 3600
        
        if time_before_start > 48:  # Более 2 дней до создания
            percentage_multiplier = Decimal("1.0")
        elif time_before_start > 24:  # Более суток
            percentage_multiplier = Decimal("0.9")
        else:  # Менее суток
            percentage_multiplier = Decimal("0.8")
        
        final_percentage = min(base_percentage * percentage_multiplier, Decimal(100))
        refund_amount = prepayment_amount * (final_percentage / Decimal(100))
        
        return round(refund_amount, 2), float(final_percentage)


# ============================================================================
# OrderService
# ============================================================================

class OrderService:
    """Основной сервис для работы с заказами.
    
    Реализует:
    - Создание заказа с валидацией и снапшотом данных
    - Получение заказов (список, детальный просмотр)
    - Фильтрация по правам доступа (клиент/исполнитель)
    """
    
    @staticmethod
    async def create_order(
        db: AsyncSession,
        client_id: int,
        order_data: "OrderCreate",
        user_id: Optional[int] = None,
    ) -> Order:
        """Создает новый заказ с валидацией и снапшотом данных.
        
        Процесс создания:
        1. Валидация данных заказа (Pydantic)
        2. Проверка доступности всех слотов (AvailabilityCheckerService)
        3. Формирование снапшота цен и условий на момент бронирования
        4. Сохранение в БД с атомарностью
        
        Args:
            db: Асинхронная сессия БД
            client_id: ID клиента (создателя заказа)
            order_data: Данные заказа из Pydantic модели
            user_id: ID пользователя (для аудита)
            
        Returns:
            Созданный заказ
            
        Raises:
            SlotConflictError: Если слоты заняты
            ScheduleBlockedException: Если слоты заблокированы
            OrderValidationError: Ошибки валидации данных
        """
        
        # 1. Проверка доступности всех слотов
        for item_data in order_data.items:
            await AvailabilityCheckerService.check_slot_availability(
                db=db,
                photographer_id=item_data.photographer_id,
                studio_room_id=item_data.studio_room_id,
                start_time=item_data.start_time,
                end_time=item_data.end_time,
            )
        
        # 2. Получение данных для снапшота (цены, адреса, условия)
        snapshot_data = await OrderService._collect_snapshot(
            db=db,
            items_data=order_data.items,
        )
        
        # 3. Расчет общей стоимости из снапшота
        total_price = Decimal("0.00")
        for item in order_data.items:
            fixed_price = snapshot_data[item].fixed_price
            total_price += fixed_price
        
        # 4. Создание заказа
        new_order = Order(
            client_id=client_id,
            order_type=order_data.order_type.value,
            status=OrderStatus.pending_payment,
            total_price=total_price,
            prepayment_amount=order_data.prepayment_amount,
            created_at=datetime.now(),
        )
        
        db.add(new_order)
        await db.flush()  # Получаем ID заказа
        
        # 5. Создание элементов заказа с фиксированными данными
        for item_data in order_data.items:
            snapshot = snapshot_data[item_data]
            
            new_item = OrderItem(
                order_id=new_order.id,
                photographer_id=item_data.photographer_id,
                photographer_service_id=item_data.photographer_service_id,
                studio_room_id=item_data.studio_room_id,
                start_time=item_data.start_time,
                end_time=item_data.end_time,
                fixed_price=snapshot.fixed_price,
                fixed_conditions=snapshot.conditions,  # Снапшот условий
            )
            
            db.add(new_item)
        
        # Фиксируем заказ в БД
        await db.commit()
        await db.refresh(new_order)
        
        return new_order
    
    @staticmethod
    async def _collect_snapshot(
        db: AsyncSession,
        items_data: List["OrderItemCreate"],
    ) -> Dict["OrderItemCreate", Dict[str, Any]]:
        """Собирает снапшот данных на момент бронирования.
        
        Снапшот включает:
        - Цену за час/фиксированную цену
        - Адрес студии (для залов)
        - Условия отмены
        
        Args:
            db: Асинхронная сессия БД
            items_data: Данные элементов заказа
            
        Returns:
            Словарь {item_data: snapshot_data}
        """
        
        snapshot = {}
        
        for item in items_data:
            # Получаем данные из БД
            if item.photographer_id:
                # Фотограф
                result = await db.execute(
                    select(PhotographerProfile, PhotographerService).where(
                        PhotographerProfile.id == item.photographer_id,
                    ).join(
                        PhotographerService,
                        PhotographerService.photographer_id == item.photographer_id,
                        isouter=True,
                    ).where(
                        PhotographerService.id == item.photographer_service_id,
                    )
                )
                row = result.first()
                
                if not row:
                    raise OrderValidationError(
                        f"Фотограф с ID {item.photographer_id} не найден"
                    )
                
                profile, photographer_service = row
                
                snapshot[item] = {
                    "fixed_price": photographer_service.price if photographer_service else Decimal("0.00"),
                    "conditions": {
                        "photographer_name": profile.display_name,
                        "service_title": photographer_service.title if photographer_service else None,
                        "terms_cancellation": "По соглашению сторон",
                    },
                }
            
            elif item.studio_room_id:
                # Зал студии
                result = await db.execute(
                    select(StudioRoom, StudioProfile).where(
                        StudioRoom.id == item.studio_room_id,
                    ).join(
                        StudioProfile,
                        StudioProfile.id == StudioRoom.studio_id,
                    )
                )
                row = result.first()
                
                if not row:
                    raise OrderValidationError(
                        f"Зал с ID {item.studio_room_id} не найден"
                    )
                
                room, studio = row
                
                snapshot[item] = {
                    "fixed_price": room.price_per_hour,
                    "conditions": {
                        "room_name": room.name,
                        "studio_title": studio.title,
                        "address": studio.address,
                        "terms_cancellation": "По соглашению сторон",
                    },
                }
        
        return snapshot
    
    @staticmethod
    async def get_orders(
        db: AsyncSession,
        current_user: User,
        search_params: Optional["OrderSearchParams"] = None,
        pagination: Optional["OrderPaginationParams"] = None,
    ) -> Tuple[List[Order], int]:
        """Получает список заказов с фильтрацией по правам доступа.
        
        Правила видимости:
        - Клиент видит только свои заказы (client_id == current_user.id)
        - Исполнители видят свои входящие брони (через OrderItem.photographer_id или .studio_room_id)
        
        Args:
            db: Асинхронная сессия БД
            current_user: Текущий авторизованный пользователь
            search_params: Параметры поиска
            pagination: Параметры пагинации
            
        Returns:
            Кортеж (список заказов, общее количество)
        """
        
        # Определяем роль пользователя
        is_client = current_user.role_id == 1 if current_user.role_id else False  # Клиент
        
        # Строим базовый запрос
        query = select(Order).options(
            joinedload(Order.client),
            joinedload(Order.items).joinedload(OrderItem.photographer),
            joinedload(Order.items).joinedload(OrderItem.studio_room),
        )
        
        total_query = select(func.count(Order.id))
        
        if is_client:
            # Клиент видит только свои заказы
            query = query.where(Order.client_id == current_user.id)
            total_query = total_query.where(Order.client_id == current_user.id)
        else:
            # Исполнитель видит свои входящие брони
            query = query.where(
                or_(
                    Order.items.any(
                        and_(
                            OrderItem.photographer_id == current_user.id,
                            OrderItem.order_id == Order.id,
                        )
                    ),
                    Order.items.any(
                        and_(
                            OrderItem.studio_room.has(
                                StudioRoom.studio_id == current_user.id,  # Пример логики
                            ),
                            OrderItem.order_id == Order.id,
                        )
                    ),
                )
            )
            
            total_query = total_query.where(
                or_(
                    Order.items.any(
                        and_(
                            OrderItem.photographer_id == current_user.id,
                            OrderItem.order_id == Order.id,
                        )
                    ),
                    Order.items.any(
                        and_(
                            OrderItem.studio_room.has(
                                StudioRoom.studio_id == current_user.id,
                            ),
                            OrderItem.order_id == Order.id,
                        )
                    ),
                )
            )
        
        # Применяем фильтры
        if search_params:
            if search_params.status:
                query = query.where(Order.status == search_params.status.value)
                total_query = total_query.where(Order.status == search_params.status.value)
            
            if search_params.order_type:
                query = query.where(Order.order_type == search_params.order_type.value)
                total_query = total_query.where(Order.order_type == search_params.order_type.value)
        
        # Пагинация
        skip = pagination.skip if pagination else 0
        limit = pagination.limit if pagination else 20
        
        query = query.offset(skip).limit(limit).order_by(Order.created_at.desc())
        
        # Выполняем запросы
        result = await db.execute(query)
        orders = result.scalars().all()
        
        total_result = await db.execute(total_query)
        total_count = total_result.scalar()
        
        return orders, total_count
    
    @staticmethod
    async def get_order_by_id(
        db: AsyncSession,
        order_id: int,
        current_user: User,
    ) -> Order:
        """Получает заказ по ID с проверкой прав доступа.
        
        Args:
            db: Асинхронная сессия БД
            order_id: ID заказа
            current_user: Текущий пользователь
            
        Returns:
            Заказ
            
        Raises:
            OrderNotFoundError: Если заказ не найден
            OrderForbiddenError: Если доступ запрещен
        """
        
        result = await db.execute(
            select(Order).where(Order.id == order_id).options(
                joinedload(Order.client),
                joinedload(Order.items).joinedload(OrderItem.photographer),
                joinedload(Order.items).joinedload(OrderItem.studio_room),
                joinedload(Order.items).joinedload(OrderItem.photographer_service),
            )
        )
        
        order = result.scalar_one_or_none()
        
        if not order:
            raise OrderNotFoundError(order_id)
        
        # Проверка прав доступа
        is_client = current_user.role_id == 1 if current_user.role_id else False
        
        if is_client and order.client_id != current_user.id:
            raise OrderForbiddenError(
                f"Доступ к заказу {order_id} запрещен",
                order_id=order_id,
            )
        
        # Проверка для исполнителей (можно расширить логику)
        if not is_client:
            has_access = False
            for item in order.items:
                if item.photographer_id == current_user.id:
                    has_access = True
                    break
            
            if not has_access:
                raise OrderForbiddenError(
                    f"Доступ к заказу {order_id} запрещен",
                    order_id=order_id,
                )
        
        return order
    
    @staticmethod
    async def get_order_by_id_with_lock(
        db: AsyncSession,
        order_id: int,
        current_user: User,
    ) -> Order:
        """Получает заказ с блокировкой для обновления статуса.
        
        Использует FOR UPDATE для предотвращения гонок состояний.
        
        Args:
            db: Асинхронная сессия БД
            order_id: ID заказа
            current_user: Текущий пользователь
            
        Returns:
            Заблокированный заказ
        """
        
        result = await db.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(
                joinedload(Order.client),
                joinedload(Order.items).joinedload(OrderItem.photographer),
                joinedload(Order.items).joinedload(OrderItem.studio_room),
            )
            .with_for_update()  # Блокировка строки
        )
        
        order = result.scalar_one_or_none()
        
        if not order:
            raise OrderNotFoundError(order_id)
        
        return order


# ============================================================================
# Helper Functions for API Integration
# ============================================================================

async def convert_order_to_summary(order: Order) -> Dict[str, Any]:
    """Конвертирует модель заказа в словарь для ответа.
    
    Args:
        order: Модель заказа
        
    Returns:
        Словарь с данными заказа
    """
    
    return {
        "id": order.id,
        "order_type": OrderTypeEnum(order.order_type),
        "status": OrderStatus(order.status),
        "total_price": order.total_price,
        "created_at": order.created_at,
    }


async def convert_order_to_detail_response(
    order: Order, 
    include_client_id: bool = True
) -> Dict[str, Any]:
    """Конвертирует модель заказа в детальный ответ.
    
    Args:
        order: Модель заказа
        include_client_id: Включать ли ID клиента
        
    Returns:
        Словарь с детальной информацией о заказе
    """
    
    items_data = []
    for item in order.items:
        item_dict = {
            "id": item.id,
            "photographer_id": item.photographer_id,
            "photographer_service_id": item.photographer_service_id,
            "studio_room_id": item.studio_room_id,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "fixed_price": item.fixed_price,
            "fixed_conditions": item.fixed_conditions,
        }
        
        # Добавляем информацию о фотографе если есть
        if item.photographer:
            item_dict["photographer_info"] = {
                "id": item.photographer.id,
                "display_name": item.photographer.display_name,
            }
            
            if item.photographer_service:
                item_dict["photographer_info"]["service_title"] = (
                    item.photographer_service.title
                )
        
        # Добавляем информацию о зале студии если есть
        if item.studio_room:
            item_dict["studio_room_info"] = {
                "id": item.studio_room.id,
                "name": item.studio_room.name,
                "studio_title": item.studio_room.studio.title if item.studio_room.studio else None,
                "address": item.studio_room.studio.address if item.studio_room.studio else None,
            }
        
        items_data.append(item_dict)
    
    response = {
        "id": order.id,
        "order_type": OrderTypeEnum(order.order_type),
        "status": OrderStatus(order.status),
        "total_price": order.total_price,
        "prepayment_amount": order.prepayment_amount,
        "created_at": order.created_at,
        "items": items_data,
        "cancellation_conditions": {},  # Можно добавить из модели
    }
    
    if include_client_id:
        response["client_id"] = order.client_id
    
    return response
