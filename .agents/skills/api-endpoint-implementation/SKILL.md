---
name: api-endpoint-implementation
description: >-
  Use this skill when implementing a new API endpoint in ReadHead-BE.
  Covers the complete flow from schema design to router to service to test.
  Activate when the user asks to "add endpoint", "implement API for X",
  "create CRUD for Y", or any task that requires a new HTTP route.
---

# API Endpoint Implementation — ReadHead-BE

## Pre-flight Checklist
```
[ ] Read .docs/api/endpoints.md — confirm endpoint does not already exist
[ ] Read .docs/database/schema.md — understand related DB tables
[ ] Read .docs/api/error-codes.md — know which error codes to use
[ ] Found a similar resource in the codebase to use as a reference pattern
```

## Step 1: Design Pydantic Schemas
File: `app/schemas/<resource>.py`

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class <Resource>Base(BaseModel):
    """Fields shared by Create and Update"""
    name: str = Field(..., min_length=1, max_length=255)

class <Resource>Create(<Resource>Base):
    """Fields required when creating a new record"""
    pass

class <Resource>Update(BaseModel):
    """All fields Optional for partial updates"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)

class <Resource>Response(<Resource>Base):
    """Fields returned to the client"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # SQLAlchemy model → Pydantic

class <Resource>PaginationData(BaseModel):
    items: list[<Resource>Response]
    total: int
    page: int
    page_size: int
    total_pages: int

class <Resource>ListResponse(BaseModel):
    data: <Resource>PaginationData
```

## Step 2: Create / Update the ORM Model
File: `app/models/<resource>.py`

Only create if it doesn't exist. Reference `.docs/database/schema.md` for exact column definitions.

## Step 3: Create the Service
File: `app/services/<resource>_service.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException

from app.models.<resource> import <Resource>
from app.schemas.<resource> import <Resource>Create, <Resource>Update

async def get_<resource>_by_id(<resource>_id: int, db: AsyncSession) -> <Resource>:
    result = await db.execute(select(<Resource>).where(<Resource>.id == <resource>_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail={
            "message": "<Resource> not found",
            "code": "<RESOURCE>_NOT_FOUND"
        })
    return obj

async def list_<resource>s(page: int, page_size: int, db: AsyncSession):
    offset = (page - 1) * page_size
    total = await db.scalar(select(func.count(<Resource>.id)))
    result = await db.execute(select(<Resource>).offset(offset).limit(page_size))
    items = result.scalars().all()
    return items, total

async def create_<resource>(data: <Resource>Create, db: AsyncSession) -> <Resource>:
    obj = <Resource>(**data.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj

async def update_<resource>(<resource>_id: int, data: <Resource>Update, db: AsyncSession):
    obj = await get_<resource>_by_id(<resource>_id, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.flush()
    await db.refresh(obj)
    return obj

async def delete_<resource>(<resource>_id: int, db: AsyncSession) -> None:
    obj = await get_<resource>_by_id(<resource>_id, db)
    await db.delete(obj)
```

## Step 4: Create the Router
File: `app/routers/<resource>s.py`

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
import math

from app.core.database import get_db
from app.schemas.<resource> import <Resource>Create, <Resource>Update, <Resource>Response, <Resource>ListResponse
from app.services import <resource>_service

router = APIRouter(prefix="/<resource>s", tags=["<Resource>s"])

@router.get("", response_model=<Resource>ListResponse)
async def list_<resource>s(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await <resource>_service.list_<resource>s(page, page_size, db)
    return {
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": math.ceil(total / page_size),
        }
    }

@router.get("/{<resource>_id}", response_model=<Resource>Response)
async def get_<resource>(<resource>_id: int, db: AsyncSession = Depends(get_db)):
    return await <resource>_service.get_<resource>_by_id(<resource>_id, db)

@router.post("", response_model=<Resource>Response, status_code=201)
async def create_<resource>(data: <Resource>Create, db: AsyncSession = Depends(get_db)):
    return await <resource>_service.create_<resource>(data, db)

@router.patch("/{<resource>_id}", response_model=<Resource>Response)
async def update_<resource>(<resource>_id: int, data: <Resource>Update, db: AsyncSession = Depends(get_db)):
    return await <resource>_service.update_<resource>(<resource>_id, data, db)

@router.delete("/{<resource>_id}", status_code=204)
async def delete_<resource>(<resource>_id: int, db: AsyncSession = Depends(get_db)):
    await <resource>_service.delete_<resource>(<resource>_id, db)
```

## Step 5: Register the Router
In `app/routers/router.py`:
```python
from app.routers.<resource>s import router as <resource>s_router
api_router.include_router(<resource>s_router)
```

## Step 6: Write Tests
File: `tests/integration/test_<resource>s_api.py`

Cover these cases:
- `GET /<resource>s` → 200, returns list
- `GET /<resource>s/{id}` → 200, returns object
- `GET /<resource>s/9999` → 404
- `POST /<resource>s` valid data → 201
- `POST /<resource>s` invalid data → 422
- `PATCH /<resource>s/{id}` → 200
- `DELETE /<resource>s/{id}` → 204

## Step 7: Update Docs
Add the new endpoint(s) to `.docs/api/endpoints.md`.

## Step 8: Validate
```bash
pytest tests/integration/test_<resource>s_api.py -v
black --check app/
```
