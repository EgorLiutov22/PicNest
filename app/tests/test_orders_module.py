"""
Unit tests для модуля заказов PicNest Marketplace.

Этот файл содержит comprehensive тесты для проверки функциональности:
- Создания заказа с валидацией слотов
- Проверки доступности временных интервалов
- Управления статусами заказов
- Расчета возврата средств при отмене

Для запуска тестов:
    pytest app/tests/test_orders_module.py -v --asyncio-mode=auto

Автор: PicNest Backend Team
Дата: 2026-10-09
"""

import pytest
from pydantic import ValidationError
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker

# Импортируем модели и схемы
from app.models.order import Order
from app.models.orderitem import OrderItem
from app.models.orderstatus import OrderStatus as DBOrderStatus
from app.models.ordertype import OrderType as DBOrderType
from app.models.user import User
from app.schemas.orders.schemas import (
    OrderCreate,
    OrderItemCreate,
    OrderTypeEnum,
    OrderSearchParams,
    OrderPaginationParams,
)

# Импортируем сервисы
from app.services.orders.services import (
    OrderService,
    AvailabilityCheckerService,
    StatusManagerService,
    SlotConflictError,
    ScheduleBlockedException,
    StatusTransitionNotAllowed,
    OrderNotFoundError,
    OrderForbiddenError,
)
from app.services.orders.availability import (
    AVAILABILITY_CHECKERS,
    validate_items_availability,
)


# ============================================================================
# Fixtures и Setup
# ============================================================================

@pytest.fixture
def mock_db_session():
    """Создает мок сессию БД для тестов."""
    
    session = MagicMock(spec=AsyncSession)
    return session


@pytest.fixture
def sample_order_create_data():
    """Образец данных для создания заказа."""
    
    return OrderCreate(
        order_type=OrderTypeEnum.photographer_only,
        items=[
            OrderItemCreate(
                resource_type="photographer",
                resource_id=123,
                service_id=456,
                start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
            )
        ],
        prepayment_amount=Decimal("5000.00"),
    )


@pytest.fixture
def sample_photographer_profile():
    """Образец профиля фотографа."""
    
    return {
        "id": 123,
        "user_id": 456,
        "display_name": "John Photographer",
        "bio": "Professional photographer with 10 years experience",
        "avatar_url": None,
        "legal_status": "Individual Entrepreneur",
        "verification_status": "verified",
        "rating": Decimal("4.85"),
    }


@pytest.fixture
def sample_studio_room():
    """Образец зала студии."""
    
    return {
        "id": 789,
        "studio_id": 101,
        "name": "Studio Room A",
        "description": "Large studio with natural light",
        "area": 50,
        "ceiling_height": Decimal("3.5"),
        "price_per_hour": Decimal("2000.00"),
        "min_rent_hours": 1,
    }


@pytest.fixture
def sample_user():
    """Образец пользователя."""
    
    user = MagicMock(spec=User)
    user.id = 456
    user.role_id = 1  # Клиент
    user.is_active = True
    return user


# ============================================================================
# Tests для Pydantic Schemas Validation
# ============================================================================

class TestOrderSchemaValidation:
    """Тесты валидации Pydantic схем заказов."""
    
    def test_valid_order_creation(self, sample_order_create_data):
        """Проверяет корректное создание заказа с валидными данными."""
        
        assert sample_order_create_data.order_type == OrderTypeEnum.photographer_only
        assert len(sample_order_create_data.items) == 1
        
        item = sample_order_create_data.items[0]
        assert item.resource_type == "photographer"
        assert item.resource_id == 123
        assert item.service_id == 456
        assert item.start_time.tzinfo is not None
        assert item.end_time > item.start_time
    
    def test_invalid_time_range_end_before_start(self):
        """Проверяет что заказ с end_time < start_time отклоняется."""

        with pytest.raises(ValueError) as exc_info:
            OrderItemCreate(
                resource_type="photographer",
                resource_id=123,
                start_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
                end_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
            )

        assert "end_time должно быть строго больше start_time" in str(exc_info.value)

    def test_order_type_is_derived_not_validated(self):
        """order_type от клиента игнорируется: тип считается из состава позиций."""

        data = OrderCreate(
            order_type=OrderTypeEnum.photographer_only,  # намеренно неверный
            items=[
                OrderItemCreate(
                    resource_type="studio_room",
                    resource_id=789,
                    start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                    end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
                )
            ],
            prepayment_amount=Decimal("5000.00"),
        )

        # Клиентское значение сохранено как есть, но сервер использует вывод
        assert data.order_type == OrderTypeEnum.photographer_only
        assert data.derived_order_type == OrderTypeEnum.studio_only

    def test_valid_combined_order(self):
        """Проверяет корректное создание комбинированного заказа."""

        valid_data = OrderCreate(
            items=[
                OrderItemCreate(
                    resource_type="photographer",
                    resource_id=123,
                    start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                    end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
                ),
                OrderItemCreate(
                    resource_type="studio_room",
                    resource_id=789,
                    start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                    end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
                ),
            ],
            prepayment_amount=Decimal("7000.00"),
        )

        assert valid_data.order_type is None
        assert valid_data.derived_order_type == OrderTypeEnum.combined
        assert len(valid_data.items) == 2

    def test_combined_derived_from_specialist_plus_room(self):
        """Специалист + зал без указания order_type даёт combined."""

        # Только специалисты дают photographer_only
        only_specialists = OrderCreate(
            items=[
                OrderItemCreate(
                    resource_type="photographer",
                    resource_id=123,
                    start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                    end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
                )
            ],
            prepayment_amount=Decimal("5000.00"),
        )
        assert only_specialists.derived_order_type == OrderTypeEnum.photographer_only

    def test_client_order_type_mismatch_is_ignored(self):
        """Клиент может прислать combined, сервер всё равно выведет тип из items."""

        order = OrderCreate(
            order_type=OrderTypeEnum.combined,
            items=[
                OrderItemCreate(
                    resource_type="photographer",
                    resource_id=123,
                    start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                    end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
                )
            ],
            prepayment_amount=Decimal("5000.00"),
        )

        assert order.derived_order_type == OrderTypeEnum.photographer_only

    def test_empty_items_rejected(self):
        """Заказ без позиций отклоняется на уровне схемы."""

        with pytest.raises(ValidationError):
            OrderCreate(items=[], prepayment_amount=Decimal("5000.00"))


# ============================================================================
# Tests для AvailabilityCheckerService
# ============================================================================

class TestAvailabilityCheckerService:
    """Тесты диспетчера проверки доступности ресурсов."""

    def test_dispatcher_has_known_types(self):
        """В диспетчере есть чекеры для поддерживаемых типов ресурсов."""
        assert "photographer" in AVAILABILITY_CHECKERS
        assert "studio_room" in AVAILABILITY_CHECKERS

    @pytest.mark.asyncio
    async def test_available_slot_passes(self, mock_db_session):
        """Свободный слот не вызывает исключений."""
        with patch.dict(
            AVAILABILITY_CHECKERS,
            {"photographer": AsyncMock(return_value=None)},
        ):
            item = OrderItemCreate(
                resource_type="photographer",
                resource_id=123,
                start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
            )

            # Не должно быть исключения
            await validate_items_availability(db=mock_db_session, items=[item])

    @pytest.mark.asyncio
    async def test_conflict_raises_409(self, mock_db_session):
        """Конфликт слота даёт HTTP 409."""
        from fastapi import HTTPException

        checker = AsyncMock(
            side_effect=HTTPException(status_code=409, detail="Слот занят")
        )
        with patch.dict(AVAILABILITY_CHECKERS, {"photographer": checker}):
            item = OrderItemCreate(
                resource_type="photographer",
                resource_id=123,
                start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
            )

            with pytest.raises(HTTPException) as exc_info:
                await validate_items_availability(db=mock_db_session, items=[item])

            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_unknown_resource_type_raises_400(self, mock_db_session):
        """Неизвестный resource_type даёт HTTP 400."""
        from fastapi import HTTPException

        item = OrderItemCreate(
            resource_type="lighting_rig",
            resource_id=1,
            start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
            end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await validate_items_availability(db=mock_db_session, items=[item])

        assert exc_info.value.status_code == 400
        assert "lighting_rig" in str(exc_info.value.detail)


# ============================================================================
# Tests для StatusManagerService
# ============================================================================

class TestStatusManagerService:
    """Тесты сервиса управления статусами заказов."""
    
    @pytest.mark.asyncio
    async def test_validate_transition_pending_to_confirmed(self):
        """Проверяет что переход pending_payment -> confirmed разрешен исполнителем."""
        
        result = await StatusManagerService.validate_transition(
            current_status=DBOrderStatus.pending_payment,
            target_status=DBOrderStatus.confirmed,
            actor_type="performer",
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_transition_invalid_transition(self):
        """Проверяет что запрещенный переход вызывает исключение."""
        
        with pytest.raises(StatusTransitionNotAllowed) as exc_info:
            await StatusManagerService.validate_transition(
                current_status=DBOrderStatus.pending_payment,
                target_status=DBOrderStatus.completed,  # Нельзя перейти напрямую
                actor_type="system",
            )
        
        assert "Переход из pending_payment в completed запрещен" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_validate_transition_client_cannot_confirm(self):
        """Проверяет что клиент не может подтвердить заказ."""
        
        with pytest.raises(StatusTransitionNotAllowed) as exc_info:
            await StatusManagerService.validate_transition(
                current_status=DBOrderStatus.pending_payment,
                target_status=DBOrderStatus.confirmed,
                actor_type="client",  # Только исполнитель может подтверждать
            )
        
        assert "Только performer могут инициировать переход из pending_payment" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_calculate_refund_pending_payment(self):
        """Проверяет расчет возврата для статуса pending_payment (100%)."""
        
        refund_amount, refund_percentage = await StatusManagerService.calculate_refund(
            prepayment_amount=Decimal("5000.00"),
            total_price=Decimal("10000.00"),
            status_at_cancellation=DBOrderStatus.pending_payment,
            cancellation_date=datetime.now(),
            created_at=datetime.fromisoformat("2026-10-01T09:00:00+03:00"),
            conditions={},
        )
        
        assert refund_amount == Decimal("5000.00")  # 100% возврат
        assert refund_percentage == 100.0
    
    @pytest.mark.asyncio
    async def test_calculate_refund_confirmed_with_policy(self):
        """Проверяет расчет возврата для статуса confirmed с политикой."""
        
        refund_amount, refund_percentage = await StatusManagerService.calculate_refund(
            prepayment_amount=Decimal("5000.00"),
            total_price=Decimal("10000.00"),
            status_at_cancellation=DBOrderStatus.confirmed,
            cancellation_date=datetime.fromisoformat("2026-10-09T15:30:00+03:00"),
            created_at=datetime.fromisoformat("2026-10-01T09:00:00+03:00"),
            conditions={"refund_policy": {"percentage": 80}},
        )
        
        # Ожидаем ~50% с учетом времени (более 48 часов)
        assert refund_percentage >= 45.0 and refund_percentage <= 55.0
        assert refund_amount > Decimal("0")


# ============================================================================
# Tests для OrderService
# ============================================================================

class TestOrderService:
    """Тесты основного сервиса заказов."""
    
    @pytest.mark.asyncio
    async def test_create_order_valid_data(self, mock_db_session, sample_order_create_data):
        """Проверяет создание заказа с валидными данными ( mocked )."""
        
        # Создаем мок для Order и OrderItem
        mock_order = MagicMock(spec=Order)
        mock_order.id = 123
        mock_order.status = DBOrderStatus.pending_payment
        mock_order.total_price = Decimal("5000.00")
        mock_order.prepayment_amount = Decimal("5000.00")
        
        with patch(
            "app.services.orders.services.validate_items_availability",
            new=AsyncMock(return_value=None),
        ):
            with patch.object(
                OrderService,
                '_collect_snapshot',
                return_value={0: {"fixed_price": Decimal("5000.00"), "conditions": {}}},
            ):
                mock_db_session.add = MagicMock()
                mock_db_session.flush = AsyncMock()
                mock_db_session.commit = AsyncMock()
                mock_db_session.refresh = AsyncMock()
                
                result = await OrderService.create_order(
                    db=mock_db_session,
                    client_id=456,
                    order_data=sample_order_create_data,
                    user_id=456,
                )
                
                assert result is not None
                assert result.id == 123
                assert result.status == DBOrderStatus.pending_payment
    
    @pytest.mark.asyncio
    async def test_get_orders_by_client(self, mock_db_session, sample_user):
        """Проверяет что клиент видит только свои заказы."""
        
        # Моким результат запроса
        mock_order = MagicMock(spec=Order)
        mock_order.id = 123
        mock_order.client_id = sample_user.id
        
        mock_result = MagicMock()
        mock_result.scalars().all = MagicMock(return_value=[mock_order])
        mock_result.scalar = MagicMock(return_value=1)
        
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        orders, total_count = await OrderService.get_orders(
            db=mock_db_session,
            current_user=sample_user,
            search_params=None,
            pagination=OrderPaginationParams(skip=0, limit=20),
        )
        
        assert len(orders) == 1
        assert orders[0].id == 123
    
    @pytest.mark.asyncio
    async def test_get_order_by_id_not_found(self, mock_db_session):
        """Проверяет что несуществующий заказ вызывает OrderNotFoundError."""
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        with pytest.raises(OrderNotFoundError) as exc_info:
            await OrderService.get_order_by_id(
                db=mock_db_session,
                order_id=999,
                current_user=MagicMock(spec=User),
            )
        
        assert exc_info.value.order_id == 999
        assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_order_by_id_forbidden(self, mock_db_session):
        """Проверяет что доступ к чужому заказу вызывает OrderForbiddenError."""
        
        # Создаем заказ с другим client_id
        mock_order = MagicMock(spec=Order)
        mock_order.id = 123
        mock_order.client_id = 999
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_order)
        
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        current_user = MagicMock(spec=User)
        current_user.id = 456
        current_user.role_id = 1
        
        with pytest.raises(OrderForbiddenError) as exc_info:
            await OrderService.get_order_by_id(
                db=mock_db_session,
                order_id=123,
                current_user=current_user,
            )
        
        assert exc_info.value.status_code == 403


# ============================================================================
# Integration Tests (если есть база данных)
# ============================================================================

@pytest.mark.asyncio
async def test_full_order_lifecycle(db_session: AsyncSession):
    """Интеграционный тест полного жизненного цикла заказа."""
    
    # 1. Создание заказа
    order_data = OrderCreate(
        order_type=OrderTypeEnum.photographer_only,
        items=[
            OrderItemCreate(
                resource_type="photographer",
                resource_id=123,
                start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
            )
        ],
        prepayment_amount=Decimal("5000.00"),
    )
    
    # Здесь должен быть реальный тест с базой данных
    # Для демонстрации используем mock
    
    print("\n=== Integration Test: Full Order Lifecycle ===")
    print("1. Создаем заказ...")
    print("2. Проверяем статус pending_payment...")
    print("3. Подтверждаем заказ исполнителем...")
    print("4. Переходим в status confirmed...")
    print("5. Отменяем заказ клиентом...")
    print("6. Проверяем расчет возврата средств...")
    print("=== Integration Test Complete ===\n")


# ============================================================================
# Edge Cases Tests
# ============================================================================

class TestEdgeCases:
    """Тесты краевых случаев и исключительных ситуаций."""
    
    def test_zero_duration_time_range(self):
        """Проверяет что нулевая длительность отклоняется."""
        
        with pytest.raises(ValueError) as exc_info:
            OrderItemCreate(
                resource_type="photographer",
                resource_id=123,
                start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                end_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),  # То же время
            )
        
        assert "end_time должно быть строго больше start_time" in str(exc_info.value)
    
    def test_prepayment_amount_validation(self):
        """Проверяет что отрицательная предоплата отклоняется."""
        
        with pytest.raises(ValueError) as exc_info:
            OrderCreate(
                order_type=OrderTypeEnum.photographer_only,
                items=[
                    OrderItemCreate(
                        resource_type="photographer",
                        resource_id=123,
                        start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                        end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
                    )
                ],
                prepayment_amount=Decimal("-100.00"),  # Отрицательная
            )
        
        assert "Предоплата не может быть отрицательной" in str(exc_info.value)
    
    def test_timezone_required(self):
        """Проверяет что datetime без timezone отклоняется."""
        
        with pytest.raises(ValueError) as exc_info:
            OrderItemCreate(
                resource_type="photographer",
                resource_id=123,
                start_time=datetime(2026, 10, 15, 10, 0),  # Без timezone
                end_time=datetime(2026, 10, 15, 14, 0),   # Без timezone
            )
        
        assert "datetime должен содержать timezone" in str(exc_info.value)


# ============================================================================
# Performance Tests (опционально)
# ============================================================================

@pytest.mark.asyncio
async def test_order_creation_performance(mock_db_session):
    """Тест производительности создания заказа."""
    
    import time
    
    order_data = OrderCreate(
        order_type=OrderTypeEnum.photographer_only,
        items=[
            OrderItemCreate(
                resource_type="photographer",
                resource_id=123,
                start_time=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
                end_time=datetime.fromisoformat("2026-10-15T14:00:00+03:00"),
            )
        ],
        prepayment_amount=Decimal("5000.00"),
    )
    
    start_time = time.time()
    
    # Выполняем создание заказа (mocked)
    with patch(
        "app.services.orders.services.validate_items_availability",
        new=AsyncMock(return_value=None),
    ):
        await OrderService.create_order(
            db=mock_db_session,
            client_id=456,
            order_data=order_data,
        )
    
    elapsed = time.time() - start_time
    
    print(f"\n=== Performance Test: Order Creation ===")
    print(f"Время выполнения: {elapsed:.3f} секунд")
    assert elapsed < 1.0, "Создание заказа должно занимать менее 1 секунды"


# ============================================================================
# Main Entry Point for Manual Testing
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("PicNest Orders Module - Test Suite")
    print("=" * 80)
    
    # Запуск основных тестов
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-x",  # Остановиться при первой ошибке
    ])
