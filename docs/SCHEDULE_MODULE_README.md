# PicNest Schedule Management Module - Complete Implementation Guide

## 📚 Overview

This document provides a comprehensive guide to the **Schedule Management Module** for the PicNest Marketplace. The module implements complete CRUD operations for managing photographer and studio room schedules with full RBAC (Role-Based Access Control) support.

## 🎯 What's Included

### Core Components Created

| Component | Files | Purpose |
|-----------|-------|---------|
| **Models** | `app/models/schedule.py` | SQLAlchemy ORM models for ScheduleTemplate, ScheduleException, ScheduleBlock |
| **Schemas** | `app/schemas/schedule/schemas.py` | Pydantic v2 validation schemas with strict type checking |
| **Services** | `app/services/schedule/services.py` | Business logic with RBAC checks and conflict detection |
| **API Endpoints** | `app/routers/schedule/router.py` | RESTful FastAPI endpoints with proper error handling |
| **Migrations** | `app/core/migrations/add_schedule_block.py` | Database migration script for schedule_blocks table |
| **Tests** | `app/tests/test_schedule.py` | Comprehensive unit and integration tests |

### Documentation Created

| Document | Description | Location |
|----------|-------------|----------|
| Module Guide | Complete module documentation with examples | [docs/schedule_management.md](schedule_management.md) |
| API Spec | Detailed API specification with all endpoints | [docs/schedule_api.md](schedule_api.md) |
| File Summary | List of all created files and structure | [docs/SCHEDULE_MODULE_FILES.md](SCHEDULE_MODULE_FILES.md) |
| Quick Reference | Summary and quick start guide | [docs/SCHEDULE_MODULE_SUMMARY.md](SCHEDULE_MODULE_SUMMARY.md) |

## 🏗 Architecture

The module follows **Clean Architecture** principles:

```
┌─────────────────────────────────────────────────────────────┐
│                   Presentation Layer                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │   FastAPI Router (app/routers/schedule/router.py)    │  │
│  │   - REST endpoints                                   │  │
│  │   - Input validation via Pydantic v2                 │  │
│  │   - Error handling with proper HTTP status codes     │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                     Business Layer                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │   Service Classes (app/services/schedule/)           │  │
│  │   - ScheduleTemplateService                          │  │
│  │   - ScheduleExceptionService                         │  │
│  │   - ScheduleBlockService                             │  │
│  │   - RBAC access control checks                       │  │
│  │   - Conflict detection                               │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                      Data Layer                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │   SQLAlchemy Models (app/models/schedule.py)         │  │
│  │   - ScheduleTemplate                                 │  │
│  │   - ScheduleException                                │  │
│  │   - ScheduleBlock                                    │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    Schema Layer                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │   Pydantic Schemas (app/schemas/schedule/)           │  │
│  │   - Input validation schemas                         │  │
│  │   - Response schemas                                 │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 📋 Key Features Implemented

### ✅ Schedule Templates (Weekly Patterns)

- Create weekly schedule templates for photographers and studio rooms
- Define working hours by day of week (1=Monday, 7=Sunday)
- Strict validation: start_time must be strictly less than end_time
- Bulk creation support for all days at once

**Example:**
```python
{
    "owner_id": 1,
    "owner_type": "photographer",
    "day_of_week": 1,  # Monday
    "start_time": "09:00:00",
    "end_time": "18:00:00"
}
```

### ✅ Schedule Exceptions (Day-off and Custom Time)

- Create exceptions for specific dates
- Set days off (`is_day_off=true`) without specifying times
- Set custom working hours for specific dates
- Exception priority over weekly templates for that date
- Duplicate prevention (one exception per date per owner)

**Example - Day Off:**
```python
{
    "owner_id": 1,
    "owner_type": "photographer",
    "date": "2024-12-31",
    "is_day_off": true
}
```

**Example - Custom Hours:**
```python
{
    "owner_id": 1,
    "owner_type": "photographer",
    "date": "2025-01-01",
    "is_day_off": false,
    "custom_start_time": "10:00:00",
    "custom_end_time": "16:00:00"
}
```

### ✅ Schedule Blocks (Slot Blocking)

- Manually block time periods to prevent booking conflicts
- Prevent double-booking for third-party reservations
- Automatic conflict detection with existing blocks
- Optional reason field for documentation

**Example:**
```python
{
    "owner_id": 1,
    "owner_type": "photographer",
    "start_datetime": "2024-12-25",
    "end_datetime": "2024-12-26",
    "reason": "New Year holidays"
}
```

## 🔐 RBAC (Role-Based Access Control)

### User Roles and Permissions

| Role | Can Edit Own Schedule? | Can Edit Others' Schedule? | Scope of Access |
|------|------------------------|----------------------------|-----------------|
| **photographer** | ✅ Yes | ❌ No | Only own profile |
| **studio** | ✅ Yes (for own rooms) | ❌ No | Only own studio's rooms |
| **admin** | ✅ Yes | ✅ Yes | All schedules |

### Access Control Examples

```python
# Photographer can edit own schedule - SUCCESS
user_id = "photographer-user-123"
profile.user_id = "photographer-user-123"  # Same user → Allowed

# Photographer cannot edit others' schedule - FORBIDDEN  
user_id = "photographer-user-123"
profile.user_id = "photographer-user-456"  # Different user → Forbidden (HTTP 403)

# Studio rep can edit own rooms - SUCCESS
current_user.role = "studio"
current_user.studio_profile_id = 1
room.studio_id = 1  # Same studio → Allowed

# Studio rep cannot edit other studios' rooms - FORBIDDEN
current_user.studio_profile_id = 1
room.studio_id = 2  # Different studio → Forbidden (HTTP 403)
```

## 📊 Data Validation Rules

### Time Validation

All time ranges must satisfy: **start_time < end_time** (strictly less than)

| Scenario | Valid? | Reason |
|----------|--------|--------|
| `09:00` to `18:00` | ✅ Yes | Normal working hours |
| `09:00` to `09:00` | ❌ No | Times must be different |
| `18:00` to `09:00` | ❌ No | End before start is invalid |

### Day of Week Validation

Must be in range **1-7** where:
- 1 = Monday (Monday)
- 2 = Tuesday (Tuesday)
- 3 = Wednesday (Wednesday)
- 4 = Thursday (Thursday)
- 5 = Friday (Friday)
- 6 = Saturday (Saturday)
- 7 = Sunday (Sunday)

### Date Validation for Blocks

Must satisfy: **start_datetime < end_datetime** (strictly less than)

| Scenario | Valid? | Reason |
|----------|--------|--------|
| `2024-12-25` to `2024-12-26` | ✅ Yes | Valid range |
| `2024-12-26` to `2024-12-25` | ❌ No | End before start |
| `2024-12-25` to `2024-12-25` | ❌ No | Must be different dates |

### Conflict Detection

**Schedule Blocks:** New blocks cannot overlap with existing blocks for the same owner.

Overlap detection logic:
```python
# Two date ranges overlap if:
start1 < end2 AND start2 < end1
```

## 🚀 Getting Started

### Step 1: Install Dependencies

```bash
cd PicNest
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required variables:
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - JWT signing key (min 32 chars)

### Step 3: Run Database Migration

Create the `schedule_blocks` table:

```bash
python -m app.core.migrations.add_schedule_block
```

Expected output on success:
```
✅ Миграция успешно выполнена! Таблица schedule_blocks создана.
```

### Step 4: Connect Router to Main App

Add this line to `app/main.py`:

```python
from app.routers.schedule import router as schedule_router

# After existing imports and before app.run()
app.include_router(schedule_router, prefix="/api/v1/schedules", tags=["Schedule Management"])
```

### Step 5: Start the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 6: Test the API

Visit interactive documentation at: http://localhost:8000/docs

## 📡 API Endpoints Reference

All endpoints require JWT authentication in `Authorization` header:
```
Authorization: Bearer <access_token>
```

### Schedule Templates

| Method | Endpoint | Description | Status Code |
|--------|----------|-------------|-------------|
| POST | `/api/v1/schedules/templates` | Create template | 201 Created |
| GET | `/api/v1/schedules/templates` | List templates (paginated) | 200 OK |
| GET | `/api/v1/schedules/templates/{id}` | Get by ID | 200 OK / 404 Not Found |
| PUT | `/api/v1/schedules/templates/{id}` | Update template | 200 OK / 403 Forbidden |
| DELETE | `/api/v1/schedules/templates/{id}` | Delete template | 200 OK / 404 Not Found |
| POST | `/api/v1/schedules/templates/bulk` | Bulk create templates | 201 Created |

### Schedule Exceptions

| Method | Endpoint | Description | Status Code |
|--------|----------|-------------|-------------|
| POST | `/api/v1/schedules/exceptions` | Create exception | 201 Created / 409 Conflict |
| GET | `/api/v1/schedules/exceptions` | List exceptions (paginated) | 200 OK |
| GET | `/api/v1/schedules/exceptions/{id}` | Get by ID | 200 OK / 404 Not Found |
| PUT | `/api/v1/schedules/exceptions/{id}` | Update exception | 200 OK / 403 Forbidden |
| DELETE | `/api/v1/schedules/exceptions/{id}` | Delete exception | 200 OK / 404 Not Found |

### Schedule Blocks

| Method | Endpoint | Description | Status Code |
|--------|----------|-------------|-------------|
| POST | `/api/v1/schedules/blocks` | Create block | 201 Created / 409 Conflict |
| GET | `/api/v1/schedules/blocks` | List blocks (paginated) | 200 OK |
| GET | `/api/v1/schedules/blocks/{id}` | Get by ID | 200 OK / 404 Not Found |
| DELETE | `/api/v1/schedules/blocks/{id}` | Unblock slot | 200 OK / 403 Forbidden |

## ❌ Error Handling and Status Codes

All errors follow the standard format:
```json
{
    "detail": "<error message>"
}
```

### HTTP Status Codes Used

| Code | Exception Class | When Returned | Example Message |
|------|-----------------|---------------|-----------------|
| **400** | `ScheduleValidationError` | Invalid input data | "Время начала работы должно быть строго меньше времени окончания" |
| **403** | `ScheduleAccessDeniedError` | Insufficient permissions | "Фотограф может редактировать только своё расписание" |
| **404** | `ScheduleNotFoundError` | Resource not found | "Шаблон расписания с ID 42 не найден" |
| **409** | `ScheduleConflictError` | Data conflict | "Новая блокировка пересекается с существующей блокировкой" |

## 🧪 Testing

### Run All Tests

```bash
pytest app/tests/test_schedule.py -v --asyncio-mode=auto
```

### Run Specific Test Class

```bash
pytest app/tests/test_schedule.py::TestScheduleTemplateService -v
```

### Integration Tests (requires database)

Integration tests that require a PostgreSQL connection are marked with `@pytest.mark.integration`:

```bash
pytest app/tests/test_schedule.py -m integration -v
```

Set environment variable to run:
```bash
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/picnest"
pytest app/tests/test_schedule.py -m integration -v
```

## 📈 Performance Considerations

### Database Indexes

The module includes indexes for optimal query performance:

- `idx_schedule_blocks_dates` on `schedule_blocks(start_datetime, end_datetime)`
- `idx_schedule_exceptions_date` on `schedule_exceptions(date)`

### Pagination Limits

List endpoints support pagination with maximum limit of **1000 records** per request to prevent excessive data transfer.

## 🔧 Troubleshooting

### Issue: Migration fails with "table already exists" error

**Solution:** This is expected if migration was run before. The script checks for existing table and skips creation if present. No action needed.

### Issue: HTTP 403 Forbidden when accessing schedule endpoints

**Possible causes:**
1. Using wrong owner_id that doesn't belong to your profile
2. Trying to access another user's studio room schedules without admin role
3. JWT token expired or invalid

**Solution:** Verify you're using correct owner_id matching your user profile, and check your token status.

### Issue: HTTP 409 Conflict when creating blocks

**Cause:** New block overlaps with existing block for same owner.

**Solution:** Check existing blocks first:
```bash
GET /api/v1/schedules/blocks?owner_id=1&owner_type=photographer
```

Then adjust your new block's date range to avoid overlap.

### Issue: Time validation error despite valid times

**Cause:** String format might be incorrect.

**Solution:** Ensure time strings are in `HH:MM:SS` 24-hour format:
- ✅ `"09:00:00"`
- ❌ `"9:00 AM"` or `"09:00"` (incomplete)

## 📚 Additional Resources

### Official Documentation
- [Module Guide](docs/schedule_management.md) - Complete feature documentation
- [API Specification](docs/schedule_api.md) - Full endpoint reference with examples
- [File Summary](docs/SCHEDULE_MODULE_FILES.md) - All created files listed
- [Quick Reference](docs/SCHEDULE_MODULE_SUMMARY.md) - Fast lookup guide

### Code Files
- [Models](app/models/schedule.py) - SQLAlchemy ORM definitions
- [Schemas](app/schemas/schedule/schemas.py) - Pydantic validation schemas
- [Services](app/services/schedule/services.py) - Business logic layer
- [Router](app/routers/schedule/router.py) - API endpoints

### Test Files
- [Unit Tests](app/tests/test_schedule.py) - Comprehensive test suite

## 🤝 Contributing

When extending this module:

1. Follow existing code structure and naming conventions
2. Add appropriate type hints (Python 3.11+)
3. Include docstrings for all public functions/classes
4. Write tests for new functionality
5. Update documentation if API contracts change

## 📝 Changelog

### Version 1.0.0 (October 2026)

**Initial Release**

- ✅ ScheduleTemplate model and CRUD operations
- ✅ ScheduleException model with day-off support
- ✅ ScheduleBlock model for slot blocking
- ✅ Full RBAC implementation (photographer/studio/admin roles)
- ✅ Pydantic v2 strict validation
- ✅ Conflict detection for blocks and exceptions
- ✅ RESTful API endpoints with proper error handling
- ✅ Database migration scripts
- ✅ Comprehensive test suite
- ✅ Full documentation

---

**Module Version:** 1.0.0  
**Created:** October 2026  
**Team:** PicNest Backend Development Team  
**License:** All rights reserved © 2026 PicNest Marketplace
