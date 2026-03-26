"""Health check routes."""
from datetime import datetime
from fastapi import APIRouter

from backend.core.config import config
from backend.api.schemas import HealthResponse

router = APIRouter()


@router.get("/", response_model=HealthResponse)
async def root():
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version=config.API_VERSION,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version=config.API_VERSION,
    )
