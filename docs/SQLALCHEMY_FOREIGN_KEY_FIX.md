# SQLAlchemy Foreign Key Error - Fix Guide

## 🐛 Ошибка

```
sqlalchemy.exc.NoReferencedTableError: Foreign key associated with 
column 'order_items.photographer_service_id' could not find table 
'photographer_services' with which to generate a foreign key to target column 'id'
```

## 🔍 Причина

Ошибка возникает, когда SQLAlchemy не может найти таблицу, на которую ссылается ForeignKey. Основные причины:

1. **Модель не импортирована** в `__init__.py`
2. **Циклическая зависимость** между моделями
3. **Таблица ещё не создана** в базе данных
4. **Опечатка в названии таблицы** в `__tablename__`

## 🛠 Решения

### Решение 1: Добавить модель в __init__.py

Убедитесь, что все модели экспортированы в `app/models/__init__.py`:

```python
# Было (неправильно):
from app.models.photographerprofile import PhotographerProfile
# PhotographerService отсутствует!

# Стало (правильно):
from app.models.photographerprofile import PhotographerProfile
from app.models.photographerservice import PhotographerService  # ✅ Добавлено

__all__ = [
    "PhotographerProfile", 
    "PhotographerService",  # ✅ Экспортировано
    ...
]
```

### Решение 2: Использовать TYPE_CHECKING для циклических зависимостей

Если модели ссылаются друг на друга (циклическая зависимость), используйте `TYPE_CHECKING`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.photographerservice import PhotographerService

class OrderItem(Base):
    photographer_service: Mapped[Optional["PhotographerService"]] = relationship(...)
```

### Решение 3: Проверить название таблицы

Убедитесь, что `__tablename__` в модели совпадает с именем в ForeignKey:

```python
# Модель PhotographerService
class PhotographerService(Base):
    __tablename__ = "photographer_services"  # ✅ Должно совпадать
    
# В OrderItem
class OrderItem(Base):
    photographer_service_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("photographer_services.id", ondelete="SET NULL")
    )  # ✅ То же название таблицы
```

### Решение 4: Создать таблицу в БД

Запустите миграции или создайте таблицу вручную:

```bash
# Опционально - запустить миграции
python -m app.core.migrations.add_schedule_block

# Или через Alembic (если используется)
alembic upgrade head
```

## ✅ Исправления применены

### 1. Добавлен импорт в `__init__.py`

Файл: [`app/models/__init__.py`](../app/models/__init__.py)

```python
from app.models.photographerservice import PhotographerService

__all__ = [
    "PhotographerProfile", 
    "PhotographerService",  # ✅ Добавлено
    ...
]
```

### 2. Добавлен TYPE_CHECKING в `orderitem.py`

Файл: [`app/models/orderitem.py`](../app/models/orderitem.py)

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.photographerservice import PhotographerService

class OrderItem(Base):
    photographer_service: Mapped[Optional["PhotographerService"]] = relationship(...)
```

## 📋 Проверка исправления

После внесения изменений запустите сервер:

```bash
# Запуск приложения
uvicorn app.main:app --reload
```

Если всё правильно, вы не увидите ошибку `NoReferencedTableError`.

## 🎯 Предотвращение подобных ошибок в будущем

1. **Всегда экспортируйте модели** в `__init__.py`
2. **Используйте TYPE_CHECKING** для циклических зависимостей
3. **Проверяйте названия таблиц** перед добавлением ForeignKey
4. **Запускайте миграции** после создания новых моделей

## 📚 Ссылки

- [SQLAlchemy Foreign Key Documentation](https://docs.sqlalchemy.org/en/20/core/constraints.html#foreign-key-constraints)
- [Handling Circular Dependencies in SQLAlchemy](https://stackoverflow.com/questions/46545189/sqlalchemy-circular-imports-between-models)

---

**Дата исправления:** Октябрь 2026  
**Модель affected:** `OrderItem`, `PhotographerService`  
**Статус:** ✅ Исправлено
