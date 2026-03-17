import asyncio
from datetime import datetime
from typing import AsyncGenerator, Dict, List

from backend.api.schemas import QueryRequest, QueryResponse, SmartQueryRequest, SourceInfo
from backend.core.config import config
from backend.core.pipeline.rag_pipeline import get_pipeline
from backend.core.smart_router import get_smart_router
from backend.services.common import SSE_DONE, ServiceTimeoutError, sse_data


class QueryService:
    async def run_query(self, request: QueryRequest) -> QueryResponse:
        start_time = datetime.now()
        pipeline = get_pipeline()

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    pipeline.query,
                    query=request.query,
                    top_k=request.top_k,
                    query_date=request.query_date,
                    doc_types=request.doc_types,
                ),
                timeout=config.SERVICE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise ServiceTimeoutError("Legal query timed out") from exc

        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        sources = [SourceInfo(**s) for s in result.sources]

        return QueryResponse(
            success=True,
            query=result.query,
            answer=result.answer,
            sources=sources,
            retrieved_chunks=result.retrieved_chunks,
            processing_time_ms=round(processing_time, 2),
        )

    async def stream_query(self, request: QueryRequest, history: List[Dict]) -> AsyncGenerator[str, None]:
        pipeline = get_pipeline()
        async for chunk in pipeline.query_stream(
            query=request.query,
            top_k=request.top_k,
            query_date=request.query_date,
            doc_types=request.doc_types,
            history=history,
        ):
            yield sse_data(chunk)

        yield SSE_DONE

    async def stream_smart_query(self, request: SmartQueryRequest, history: List[Dict]) -> AsyncGenerator[str, None]:
        smart_router = get_smart_router()
        async for chunk in smart_router.route_and_stream(query=request.query, history=history):
            yield sse_data(chunk)

        yield SSE_DONE


_service: QueryService | None = None


def get_query_service() -> QueryService:
    global _service
    if _service is None:
        _service = QueryService()
    return _service
