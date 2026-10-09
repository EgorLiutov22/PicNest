# SQLAlchemy 2.0 Type Annotation Error - Fix Guide

## 🐛 Ошибка

```
sqlalchemy.orm.exc.MappedAnnotationError: Type annotation for "OrderItem.fixed_price" 
can't be correctly interpreted for Annotated Declarative Table form.
```

## 🔍 Причина

В **SQLAlchemy 2.0** все атрибуты ORM-моделей должны явно использовать типизацию `Mapped[]` для полей, которые будут маппиться в базу данных.

### ❌ Неправильно (старый стиль SQLAlchemy 1.x)

```python
class OrderItem(Base):
    fixed_price: Decimal = mapped_column(DECIMAL(10, 2), nullable=False)
    fixed_conditions: dict = mapped_column(nullable=False)
```

### ✅ Правильно (SQLAlchemy 2.0)

```python
from typing import Dict, Any

class OrderItem(Base):
    fixed_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    fixed_conditions: Mapped[Dict[str, Any]] = mapped_column(Text, nullable=False)
```

## 📋 Правило

| Тип атрибута | Аннотация | Пример |
|--------------|-----------|--------|
| **Поле БД** | `Mapped[Тип]` | `price: Mapped[float]` |
| **Классовая переменная** | `ClassVar[]` | `table_name: ClassVar[str] = "items"` |

## 🛠 Исправленные модели

### OrderItem (исправлено)

```python
class OrderItem(Base):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    
    # Исправленные поля
    fixed_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    fixed_conditions: Mapped[Dict[str, Any]] = mapped_column(Text, nullable=False)
```

## ✅ Проверка исправления

После внесения изменений запустите приложение и убедитесь, что ошибка исчезла.

```bash
# Запуск сервера для проверки
uvicorn app.main:app --reload
```

Если всё правильно, вы не увидите ошибки `MappedAnnotationError` при запуске.

## 📚 Ссылки

- [SQLAlchemy 2.0 ORM Tutorial - Annotated Declarative](https://docs.sqlalchemy.org/en/20/orm/declarative_basic.html)
- [Migration Guide: SQLAlchemy 1.x to 2.0](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html)

---

**Дата исправления:** Октябрь 2026  
**Модель:** `OrderItem`  
**Статус:** ✅ Исправлено
