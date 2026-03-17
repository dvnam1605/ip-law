"""Legal RAG query and Smart Router endpoints."""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.api.schemas import (
    QueryRequest, QueryResponse,
    SmartQueryRequest,
)
from backend.api.deps import load_history
from backend.services.common import SSE_GENERIC_ERROR, ServiceTimeoutError
from backend.services.legal import get_query_service

router = APIRouter(tags=["Query"])
logger = logging.getLogger(__name__)


@router.post("/api/query", response_model=QueryResponse)
async def query_legal(request: QueryRequest):
    try:
        service = get_query_service()
        return await service.run_query(request)
    except ServiceTimeoutError:
        raise HTTPException(
            status_code=504,
            detail={"error": "Legal query timed out"},
        )
    except Exception as e:
        logger.exception("/api/query failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail={"error": "Legal query failed"}
        )


@router.get("/api/query", response_model=QueryResponse)
async def query_legal_get(
    q: str = Query(..., description="Câu hỏi pháp luật", min_length=5),
    top_k: int = Query(5, ge=1, le=20, description="Số lượng tài liệu"),
    date: Optional[str] = Query(None, description="Ngày truy vấn (YYYY-MM-DD)")
):
    request = QueryRequest(query=q, top_k=top_k, query_date=date)
    return await query_legal(request)


@router.post("/api/query/stream")
async def query_legal_stream(request: QueryRequest):
    history = await load_history(request.session_id)
    service = get_query_service()

    async def generate():
        try:
            async for payload in service.stream_query(request, history):
                yield payload

        except Exception as e:
            logger.exception("/api/query/stream failed: %s", e)
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


@router.post("/api/smart/query/stream")
async def smart_query_stream(request: SmartQueryRequest):
    history = await load_history(request.session_id)
    service = get_query_service()

    async def generate():
        try:
            async for payload in service.stream_smart_query(request, history):
                yield payload
        except Exception as e:
            logger.exception("/api/smart/query/stream failed: %s", e)
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
