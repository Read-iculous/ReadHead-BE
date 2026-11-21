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
from uuid import UUID

@router.get("/{user_id}")
async def get_user(
    user_id: UUID,
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

### Settings with Pydantic (v2)
```python
# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    jwt_secret_key: str
    encryption_master_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
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
redis                 # Async Redis 7+ client
slowapi               # Rate limiting middleware
pydantic-settings     # Settings management (v2)
python-jose[cryptography]  # JWT
cryptography          # AES-256-GCM symmetric encryption
passlib[bcrypt]       # Password hashing
pytest
pytest-asyncio
httpx                 # Async test client
```
