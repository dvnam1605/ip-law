"""Verdict (Bản án) query endpoints."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.api.schemas import (
    VerdictQueryRequest, VerdictQueryResponse, VerdictSourceInfo,
)
from backend.api.deps import load_history
from backend.core.verdict_rag_pipeline import get_verdict_pipeline

router = APIRouter(prefix="/api/verdict", tags=["Verdict"])


@router.post("/query", response_model=VerdictQueryResponse)
async def query_verdict(request: VerdictQueryRequest):
    start_time = datetime.now()

    try:
        pipeline = get_verdict_pipeline()

        result = pipeline.query(
            query=request.query,
            top_k=request.top_k,
            ip_types=request.ip_types,
            trial_level=request.trial_level
        )

        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        sources = [VerdictSourceInfo(**s) for s in result.sources]

        return VerdictQueryResponse(
            success=True,
            query=result.query,
            answer=result.answer,
            sources=sources,
            retrieved_chunks=result.retrieved_chunks,
            processing_time_ms=round(processing_time, 2)
        )

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "processing_time_ms": round(processing_time, 2)
            }
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

    async def generate():
        try:
            pipeline = get_verdict_pipeline()

            async for chunk in pipeline.query_stream(
                query=request.query,
                top_k=request.top_k,
                ip_types=request.ip_types,
                trial_level=request.trial_level,
                history=history,
            ):
                escaped = chunk.replace('\\', '\\\\').replace('\n', '\\n')
                yield f"data: {escaped}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: [ERROR]{str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
