# 04 — Coding Standards

## Language and Style
- **Python 3.10+** — use modern features (match/case, `X | Y` type union, etc.)
- **Type hints are mandatory** on all function signatures
- **Docstrings are mandatory** on all public functions and classes
- **Black** formatter — line length 88

## Naming Conventions

### Files and modules
```
app/routers/users.py         # snake_case, plural noun
app/models/user.py           # snake_case, singular noun
app/schemas/user.py          # snake_case, singular noun
app/services/user_service.py
```

### Classes
```python
class User(Base): ...               # ORM Model: PascalCase, singular
class UserCreate(BaseModel): ...    # Pydantic: PascalCase + suffix
class UserUpdate(BaseModel): ...
class UserResponse(BaseModel): ...
class UserListResponse(BaseModel): ...
```

### Functions and variables
```python
# snake_case for all functions and variables
async def get_user_by_id(user_id: int) -> UserResponse: ...
async def create_user(data: UserCreate, db: AsyncSession) -> UserResponse: ...

# Clear prefix convention:
# get_*    → returns entity, raises 404 if not found
# list_*   → returns list, never raises
# create_* → creates new record
# update_* → updates record, raises 404 if not found
# delete_* → deletes record, raises 404 if not found
```

### Constants
```python
MAX_PAGE_SIZE = 100       # SCREAMING_SNAKE_CASE
DEFAULT_PAGE_SIZE = 20
```

## Standard Response Format

### Single resource
```json
{
  "data": { "id": 1, "name": "..." },
  "message": "Success"
}
```

### List resource
```json
{
  "data": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

### Error response
```json
{
  "detail": "User not found",
  "code": "USER_NOT_FOUND",
  "field": null
}
```

## Async Conventions
- **All DB operations must be `async`**
- Use `AsyncSession` from SQLAlchemy async
- Always `await` coroutines — never leave them un-awaited

## Error Handling
```python
# Raise HTTPException with a custom error code
raise HTTPException(
    status_code=404,
    detail={"message": "User not found", "code": "USER_NOT_FOUND"}
)
```
Full error code list: `.docs/api/error-codes.md`

## Import Order (isort)
```python
# 1. Standard library
import os
from typing import Optional

# 2. Third-party
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# 3. Local
from app.core.database import get_db
from app.schemas.user import UserCreate, UserResponse
from app.services import user_service
```

## Forbidden Patterns
- ❌ `print()` in production code — use `logging`
- ❌ Hardcoded secrets, URLs, or credentials
- ❌ `SELECT *` in raw SQL
- ❌ Bare `except:` — always catch a specific exception type
- ❌ Mutable default arguments in function signatures
- ❌ Blocking I/O inside async context
