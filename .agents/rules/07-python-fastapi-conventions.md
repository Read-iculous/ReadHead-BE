# 07 — Python / FastAPI Conventions

## Standard Project Layout
```
app/
├── __init__.py
├── main.py                    ← FastAPI app instance, router registration, middleware
├── core/
│   ├── __init__.py
│   ├── config.py              ← Pydantic Settings (reads from env vars)
│   ├── database.py            ← Async engine, session factory, get_db dependency
│   ├── auth.py                ← JWT encode/decode, get_current_user dependency
│   ├── exceptions.py          ← Custom exception classes + exception handlers
│   └── middleware.py          ← CORS, logging, request ID middleware
├── models/
│   ├── __init__.py
│   └── user.py                ← One file per resource
├── schemas/
│   ├── __init__.py
│   ├── base.py                ← BaseResponse, PaginatedResponse
│   └── user.py
├── services/
│   ├── __init__.py
│   └── user_service.py
└── routers/
    ├── __init__.py
    ├── router.py              ← Main APIRouter, includes all sub-routers
    └── users.py
```

## FastAPI Best Practices

### Dependency Injection
```python
# Always use Depends() for DB session and auth
@router.get("/{user_id}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await user_service.get_user_by_id(user_id, db)
```

### Router Definition
```python
router = APIRouter(
    prefix="/users",
    tags=["Users"],
    responses={404: {"description": "Not found"}},
)
```

### Settings with Pydantic
```python
# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    class Config:
        env_file = ".env"

settings = Settings()
```

### Database Session
```python
# app/core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

## SQLAlchemy Conventions
```python
# Models inherit from a shared Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

## Alembic (Migrations)
- Each schema change → one migration file
- Migration messages must be descriptive: `add_users_table`, `add_email_index_to_users`
- Never edit a migration file that has already been applied to any environment
- See full workflow: `.agents/skills/database-migration/SKILL.md`

## API Versioning
- Prefix all routes with `/api/v1/`
- On breaking changes → create `/api/v2/` in parallel; do not remove v1 immediately

## HTTP Status Codes
| Situation | Status Code |
|---|---|
| Resource created successfully | `201 Created` |
| Retrieve / update successful | `200 OK` |
| Delete successful | `204 No Content` |
| Resource not found | `404 Not Found` |
| Validation error | `422 Unprocessable Entity` |
| Unauthorized (not logged in) | `401 Unauthorized` |
| Forbidden (insufficient permissions) | `403 Forbidden` |
| Conflict (duplicate) | `409 Conflict` |
| Server error | `500 Internal Server Error` |

## Standard Packages
```
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
alembic
asyncpg               # PostgreSQL async driver
pydantic-settings
python-jose[cryptography]  # JWT
passlib[bcrypt]       # Password hashing
pytest
pytest-asyncio
httpx                 # Async test client
```
