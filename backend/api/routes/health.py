"""Health check routes."""
from datetime import datetime
from fastapi import APIRouter

from backend.api.schemas import HealthResponse

router = APIRouter()


@router.get("/", response_model=HealthResponse)
async def root():
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="2.0.0"
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="2.0.0"
    )
