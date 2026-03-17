import asyncio
from datetime import datetime
from typing import AsyncGenerator, Dict, List

from backend.api.schemas import VerdictQueryRequest, VerdictQueryResponse, VerdictSourceInfo
from backend.core.config import config
from backend.core.pipeline.verdict_rag_pipeline import get_verdict_pipeline
from backend.services.common import SSE_DONE, ServiceTimeoutError, sse_data


class VerdictService:
    async def run_query(self, request: VerdictQueryRequest) -> VerdictQueryResponse:
        start_time = datetime.now()
        pipeline = get_verdict_pipeline()

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    pipeline.query,
                    query=request.query,
                    top_k=request.top_k,
                    ip_types=request.ip_types,
                    trial_level=request.trial_level,
                ),
                timeout=config.SERVICE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise ServiceTimeoutError("Verdict query timed out") from exc

        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        sources = [VerdictSourceInfo(**s) for s in result.sources]

        return VerdictQueryResponse(
            success=True,
            query=result.query,
            answer=result.answer,
            sources=sources,
            retrieved_chunks=result.retrieved_chunks,
            processing_time_ms=round(processing_time, 2),
        )

    async def stream_query(self, request: VerdictQueryRequest, history: List[Dict]) -> AsyncGenerator[str, None]:
        pipeline = get_verdict_pipeline()
        async for chunk in pipeline.query_stream(
            query=request.query,
            top_k=request.top_k,
            ip_types=request.ip_types,
            trial_level=request.trial_level,
            history=history,
        ):
            yield sse_data(chunk)

        yield SSE_DONE


_service: VerdictService | None = None


def get_verdict_service() -> VerdictService:
    global _service
    if _service is None:
        _service = VerdictService()
    return _service
