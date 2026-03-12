"""Legal RAG query and Smart Router endpoints."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.api.schemas import (
    QueryRequest, QueryResponse, SourceInfo,
    SmartQueryRequest,
)
from backend.api.deps import load_history
from backend.core.rag_pipeline import get_pipeline
from backend.core.smart_router import get_smart_router

router = APIRouter(tags=["Query"])


@router.post("/api/query", response_model=QueryResponse)
async def query_legal(request: QueryRequest):
    start_time = datetime.now()

    try:
        pipeline = get_pipeline()

        result = pipeline.query(
            query=request.query,
            top_k=request.top_k,
            query_date=request.query_date,
            doc_types=request.doc_types
        )

        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        sources = [SourceInfo(**s) for s in result.sources]

        return QueryResponse(
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

    async def generate():
        try:
            pipeline = get_pipeline()

            async for chunk in pipeline.query_stream(
                query=request.query,
                top_k=request.top_k,
                query_date=request.query_date,
                doc_types=request.doc_types,
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


@router.post("/api/smart/query/stream")
async def smart_query_stream(request: SmartQueryRequest):
    history = await load_history(request.session_id)

    async def generate():
        try:
            smart_router = get_smart_router()
            async for chunk in smart_router.route_and_stream(query=request.query, history=history):
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
