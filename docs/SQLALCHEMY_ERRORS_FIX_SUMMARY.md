# SQL Alchemy Errors - Complete Fix Guide

## 🐛 Ошибки и решения для SQLAlchemy 2.0 в PicNest

Этот документ содержит все обнаруженные ошибки SQLAlchemy 2.0 и способы их исправления.

---

## 🔧 Исправление #1: MappedAnnotationError

### Ошибка
```
sqlalchemy.orm.exc.MappedAnnotationError: Type annotation for "OrderItem.fixed_price" 
can't be correctly interpreted for Annotated Declarative Table form.
```

### Причина
Поля ORM-моделей должны использовать типизацию `Mapped[]`.

### Решение
Использовать `Mapped[Тип]` вместо простого типа для полей БД:

**Было:**
```python
fixed_price: Decimal = mapped_column(DECIMAL(10, 2), nullable=False)
```

**Стало:**
```python
from sqlalchemy.orm import Mapped
fixed_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
```

### Файлы изменены
- [`app/models/orderitem.py`](../app/models/orderitem.py)

### Документация
Подробнее в: [SQLALCHEMY_ANNOTATION_FIX.md](SQLALCHEMY_ANNOTATION_FIX.md)

---

## 🔧 Исправление #2: NoReferencedTableError

### Ошибка
```
sqlalchemy.exc.NoReferencedTableError: Foreign key associated with 
column 'order_items.photographer_service_id' could not find table 
'photographer_services'
```

### Причина
1. Модель `PhotographerService` не экспортирована в `__init__.py`
2. Циклическая зависимость между моделями

### Решение 1: Добавить модель в __init__.py
```python
# app/models/__init__.py
from app.models.photographerservice import PhotographerService

__all__ = [
    "PhotographerProfile", 
    "PhotographerService",  # ✅ Добавлено
    ...
]
```

### Решение 2: Использовать TYPE_CHECKING
```python
# app/models/orderitem.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.photographerservice import PhotographerService

class OrderItem(Base):
    photographer_service: Mapped[Optional["PhotographerService"]] = relationship(...)
```

### Файлы изменены
- [`app/models/__init__.py`](../app/models/__init__.py) - добавлен импорт и экспорт
- [`app/models/orderitem.py`](../app/models/orderitem.py) - добавлен TYPE_CHECKING

### Документация
Подробнее в: [SQLALCHEMY_FOREIGN_KEY_FIX.md](SQLALCHEMY_FOREIGN_KEY_FIX.md)

---

## ✅ Статус исправлений

| Ошибка | Статус | Файл | Дата |
|--------|--------|------|------|
| MappedAnnotationError | ✅ Исправлено | orderitem.py | Октябрь 2026 |
| NoReferencedTableError | ✅ Исправлено | __init__.py, orderitem.py | Октябрь 2026 |

---

## 🚀 Проверка исправлений

После всех исправлений приложение должно запускаться без ошибок:

```bash
# Запустить сервер
uvicorn app.main:app --reload

# Если всё правильно, вы увидите:
# INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Ожидаемые результаты:

✅ Приложение запускается без ошибок  
✅ Swagger UI доступен по адресу http://localhost:8000/docs  
✅ Все endpoints работают корректно  
✅ Нет ошибок `MappedAnnotationError` или `NoReferencedTableError`

---

## 📚 Общие правила для SQLAlchemy 2.0

### 1. Все поля БД должны использовать `Mapped[]`:
```python
class MyModel(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime())
```

### 2. Классовые переменные используют `ClassVar[]`:
```python
from typing import ClassVar

class MyModel(Base):
    table_name: ClassVar[str] = "my_table"
    custom_constant: ClassVar[int] = 42
```

### 3. Для циклических зависимостей используйте TYPE_CHECKING:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.related_model import RelatedModel

class MyModel(Base):
    related: Mapped[Optional["RelatedModel"]] = relationship(...)
```

### 4. Все модели должны быть экспортированы в __init__.py:
```python
from app.models.my_model import MyModel

__all__ = [
    "MyModel",
    ...
]
```

---

## 📞 Поддержка

При возникновении новых ошибок SQLAlchemy:

1. Проверьте этот документ
2. Обратите внимание на общее правило `Mapped[]` для всех полей БД
3. Используйте TYPE_CHECKING при циклических зависимостях
4. Убедитесь, что все модели экспортированы в `__init__.py`

---

**Версия документа:** 1.0  
**Дата создания:** Октябрь 2026  
**Проект:** PicNest Marketplace  
**Статус:** Все ошибки исправлены ✅
