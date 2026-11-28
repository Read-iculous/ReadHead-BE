"""Versioned API route registration."""

from fastapi import APIRouter

from app.routers import (
    admin,
    ai,
    api_keys,
    auth,
    conversations,
    health,
    quiz,
    reading,
    sync,
    users,
)

api_router = APIRouter(prefix="/api/v1")
for module in (
    health,
    auth,
    users,
    api_keys,
    ai,
    conversations,
    reading,
    quiz,
    sync,
    admin,
):
    api_router.include_router(module.router)
