"""Public readiness and liveness endpoints."""

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse

from app.services import health_service

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def readiness() -> JSONResponse:
    """Report mandatory DB health and optional Redis degradation."""
    body, status = await health_service.health()
    return JSONResponse(jsonable_encoder(body), status_code=status)


@router.get("/live")
async def liveness() -> dict:
    """Probe process responsiveness without contacting dependencies."""
    return {"status": "alive"}
