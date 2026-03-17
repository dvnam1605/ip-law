"""Verdict (Bản án) query endpoints."""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.api.schemas import (
    VerdictQueryRequest, VerdictQueryResponse,
)
from backend.api.deps import load_history
from backend.services.common import SSE_GENERIC_ERROR, ServiceTimeoutError
from backend.services.verdict import get_verdict_service

router = APIRouter(prefix="/api/verdict", tags=["Verdict"])
logger = logging.getLogger(__name__)


@router.post("/query", response_model=VerdictQueryResponse)
async def query_verdict(request: VerdictQueryRequest):
    try:
        service = get_verdict_service()
        return await service.run_query(request)
    except ServiceTimeoutError:
        raise HTTPException(
            status_code=504,
            detail={"error": "Verdict query timed out"},
        )
    except Exception as e:
        logger.exception("/api/verdict/query failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail={"error": "Verdict query failed"}
        )


@router.get("/query", response_model=VerdictQueryResponse)
async def query_verdict_get(
    q: str = Query(..., description="Câu hỏi về tình huống/bản án", min_length=5),
    top_k: int = Query(8, ge=1, le=20, description="Số lượng tài liệu")
):
    request = VerdictQueryRequest(query=q, top_k=top_k)
    return await query_verdict(request)


@router.post("/query/stream")
async def query_verdict_stream(request: VerdictQueryRequest):
    history = await load_history(request.session_id)
    service = get_verdict_service()

    async def generate():
        try:
            async for payload in service.stream_query(request, history):
                yield payload

        except Exception as e:
            logger.exception("/api/verdict/query/stream failed: %s", e)
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
