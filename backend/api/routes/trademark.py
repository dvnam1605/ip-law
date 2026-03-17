"""Trademark search and analysis endpoints."""
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.db.schemas import (
    TrademarkSearchRequest, TrademarkSearchResponse,
    TrademarkAnalyzeRequest,
)
from backend.api.deps import load_history
from backend.services.common import SSE_GENERIC_ERROR, ServiceTimeoutError
from backend.services.trademark import get_trademark_service

router = APIRouter(prefix="/api/trademark", tags=["Trademark"])
logger = logging.getLogger(__name__)


@router.post("/search", response_model=TrademarkSearchResponse)
async def trademark_search(request: TrademarkSearchRequest):
    try:
        service = get_trademark_service()
        return await service.search(request)
    except ServiceTimeoutError:
        raise HTTPException(
            status_code=504,
            detail={"error": "Trademark search timed out"},
        )
    except Exception as e:
        logger.exception("/api/trademark/search failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail={"error": "Trademark search failed"}
        )


@router.post("/analyze/stream")
async def trademark_analyze_stream(request: TrademarkAnalyzeRequest):
    history = await load_history(request.session_id)
    service = get_trademark_service()

    async def generate():
        try:
            async for payload in service.stream_analysis(request, history):
                yield payload
        except Exception as e:
            logger.exception("/api/trademark/analyze/stream failed: %s", e)
            yield SSE_GENERIC_ERROR

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
