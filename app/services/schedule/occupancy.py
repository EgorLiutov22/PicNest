"""
Учёт занятости ресурсов.

Единственная запись занятости идёт в resource_occupancy. Пересечения
запрещает exclusion constraint occupancy_no_overlap, поэтому проверка
«свободно ли» перед INSERT не выполняется: между проверкой и вставкой
не остаётся окна для параллельного запроса.

Интервалы полуоткрытые — [start, end): бронь 14:00-15:00 и 15:00-16:00
не пересекаются.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resourceoccupancy import ResourceOccupancy


# pgcode exclusion_violation: именно он приходит от EXCLUDE, а не 23505.
EXCLUSION_VIOLATION = "23P01"

# Неоплаченный заказ держит слот ограниченное время, иначе брошенная
# корзина блокирует ресурс навсегда.
HOLD_TTL = timedelta(minutes=15)


class SlotTakenError(Exception):
    """Слот уже занят другим заказом или блокировкой."""

    def __init__(self, resource_type: str, resource_id: int, conflict: Optional[dict] = None):
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.conflict = conflict or {}
        super().__init__(f"Слот занят: {resource_type} (id={resource_id})")


def _is_exclusion_violation(exc: IntegrityError) -> bool:
    return getattr(getattr(exc, "orig", None), "pgcode", None) == EXCLUSION_VIOLATION


def _to_utc(value: datetime) -> datetime:
    """Приводит время к aware UTC.

    Проверка границ корр��ктно работает только для aware-значений: naive
    datetime сравнивается так, будто это UTC, и разница с реальным
    моментом вылезает в часовой пояс.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def occupy(
    db: AsyncSession,
    *,
    resource_type: str,
    resource_id: int,
    start_time: datetime,
    end_time: datetime,
    kind: str,
    order_item_id: Optional[int] = None,
    block_id: Optional[int] = None,
    expires_at: Optional[datetime] = None,
) -> ResourceOccupancy:
    """Занимает интервал. Конфликт отдаётся исключением, а не проверкой.

    Вставка идёт внутри транзакции вызывающего: если конфликтует хотя бы
    одна позиция составного заказа, откатываются все.
    """
    start_time = _to_utc(start_time)
    end_time = _to_utc(end_time)

    if end_time <= start_time:
        raise ValueError("Время окончания должно быть позже времени начала")

    row = ResourceOccupancy(
        resource_type=resource_type,
        resource_id=resource_id,
        period=Range(start_time, end_time, bounds="[)"),
        kind=kind,
        order_item_id=order_item_id,
        block_id=block_id,
        expires_at=expires_at,
    )
    db.add(row)

    try:
        await db.flush()
    except IntegrityError as exc:
        if not _is_exclusion_violation(exc):
            raise
        # Читать конфликт здесь нельзя: PostgreSQL уже прервал транзакцию,
        # любой следующий запрос упадёт с InFailedSQLTransaction. Текст
        # для клиента собирает вызывающий — после отката savepoint.
        raise SlotTakenError(resource_type, resource_id) from exc

    return row


async def find_conflict(
    db: AsyncSession,
    *,
    resource_type: str,
    resource_id: int,
    start_time: datetime,
    end_time: datetime,
) -> Optional[dict]:
    """Описание занятого интервала, пересекающегося с запрошенным.

    Нужен только для понятного текста ошибки клиенту: саму проверку
    делает constraint.
    """
    result = await db.execute(
        select(ResourceOccupancy)
        .where(
            ResourceOccupancy.resource_type == resource_type,
            ResourceOccupancy.resource_id == resource_id,
            ResourceOccupancy.released_at.is_(None),
            ResourceOccupancy.period.overlaps(
                Range(_to_utc(start_time), _to_utc(end_time), bounds="[)")
            ),
        )
        .limit(1)
    )
    row = result.scalars().first()
    if row is None:
        return None

    return {
        "kind": row.kind,
        "start": row.period.lower,
        "end": row.period.upper,
    }


async def find_occupied(
    db: AsyncSession,
    *,
    resource_type: str,
    resource_id: int,
    start_time: datetime,
    end_time: datetime,
) -> List[dict]:
    """Все занятые интервалы ресурса в запрошенном окне, по возрастанию.

    Один запрос по GiST-индексу. Вызовов должно быть по одному на ресурс,
    а не на элемент заказа — иначе получается N+1.
    """
    result = await db.execute(
        select(ResourceOccupancy)
        .where(
            ResourceOccupancy.resource_type == resource_type,
            ResourceOccupancy.resource_id == resource_id,
            ResourceOccupancy.released_at.is_(None),
            ResourceOccupancy.period.overlaps(
                Range(_to_utc(start_time), _to_utc(end_time), bounds="[)")
            ),
        )
        .order_by(ResourceOccupancy.period)
    )
    return [
        {"kind": row.kind, "start": row.period.lower, "end": row.period.upper}
        for row in result.scalars().all()
    ]


async def occupy_items(
    db: AsyncSession,
    items: Iterable,
    *,
    order_item_ids: Optional[List[int]] = None,
    holds: bool = True,
) -> None:
    """Занимает все позиции заказа.

    Ключевой момент: при составном заказе используется savepoint. Без него
    failed INSERT работает как «аборт» всей транзакции PostgreSQL, и
    последующие запросы сессии падают с InFailedSQLTransaction — мы не
    смогли бы даже прочитать конфликтующий интервал, чтобы объяснить
    клиенту, что именно занято.
    """
    items = list(items)
    ids = list(order_item_ids) if order_item_ids else [None] * len(items)

    # zip молча обрезает по короткому списку: часть позиций осталась бы
    # незанятой, а конфликт по ней — непойманным.
    if len(ids) != len(items):
        raise ValueError(
            f"order_item_ids ({len(ids)}) не совпадает с числом позиций ({len(items)})"
        )

    expires_at = datetime.now(timezone.utc) + HOLD_TTL if holds else None

    for item, item_id in zip(items, ids):
        try:
            async with db.begin_nested():
                await occupy(
                    db,
                    resource_type=item.resource_type,
                    resource_id=item.resource_id,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    kind="booking",
                    order_item_id=item_id,
                    expires_at=expires_at,
                )
        except SlotTakenError as exc:
            # Сообщение о конфликте строится уже после отката savepoint,
            # то есть на чистой транзакции.
            conflict = await find_conflict(
                db,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                start_time=item.start_time,
                end_time=item.end_time,
            )
            exc.conflict = conflict or {}
            raise


async def release_order(db: AsyncSession, order_id: int) -> int:
    """Освобождает слоты заказа. Возвращает число освобождённых интервалов.

    Строки не удаляются: released_at выводит их из-под действия constraint
    и из частичного GiST-индекса, а история остаётся для разбора.
    """
    result = await db.execute(
        text(
            """
            UPDATE resource_occupancy AS ro
            SET released_at = now()
            FROM order_items AS oi
            WHERE ro.order_item_id = oi.id
              AND oi.order_id = :order_id
              AND ro.released_at IS NULL
            """
        ),
        {"order_id": order_id},
    )
    return result.rowcount or 0


async def expire_stale_holds(db: AsyncSession, limit: int = 500) -> int:
    """Снимает истёкшие холды неоплаченных заказов.

    В условие частичного индекса now() вписать нельзя (предикат обязан быть
    immutable), поэтому просроченные холды освобождает этот job, а не БД.
    """
    result = await db.execute(
        text(
            """
            UPDATE resource_occupancy
            SET released_at = now()
            WHERE id IN (
                SELECT id FROM resource_occupancy
                WHERE released_at IS NULL
                  AND expires_at IS NOT NULL
                  AND expires_at < now()
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            )
            """
        ),
        {"limit": limit},
    )
    return result.rowcount or 0
