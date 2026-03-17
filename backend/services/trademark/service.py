import asyncio
from datetime import datetime
from typing import AsyncGenerator, Dict, List

from backend.core.config import config
from backend.core.pipeline.trademark_pipeline import get_trademark_pipeline
from backend.db.schemas import (
    TrademarkAnalyzeRequest,
    TrademarkResult,
    TrademarkSearchRequest,
    TrademarkSearchResponse,
)
from backend.services.common import SSE_DONE, ServiceTimeoutError, sse_data


class TrademarkService:
    async def search(self, request: TrademarkSearchRequest) -> TrademarkSearchResponse:
        start_time = datetime.now()
        pipeline = get_trademark_pipeline()
        try:
            matches = await asyncio.wait_for(
                pipeline.search_async(
                    brand_name=request.brand_name,
                    nice_classes=request.nice_classes,
                    limit=request.limit,
                ),
                timeout=config.SERVICE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise ServiceTimeoutError("Trademark search timed out") from exc

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        results = [
            TrademarkResult(
                brand_name=m.brand_name,
                owner_name=m.owner_name,
                owner_country=m.owner_country,
                registration_number=m.registration_number,
                nice_classes=m.nice_classes,
                ipr_type=m.ipr_type,
                country_of_filing=m.country_of_filing,
                status=m.status,
                status_date=m.status_date,
                similarity_score=m.similarity_score,
                match_type=m.match_type,
                st13=m.st13,
                application_number=m.application_number,
                registration_date=m.registration_date,
                application_date=m.application_date,
                expiry_date=m.expiry_date,
                feature=m.feature,
                ip_office=m.ip_office,
            )
            for m in matches
        ]

        return TrademarkSearchResponse(
            success=True,
            query=request.brand_name,
            results=results,
            total_found=len(results),
            processing_time_ms=round(processing_time, 2),
        )

    async def stream_analysis(self, request: TrademarkAnalyzeRequest, history: List[Dict]) -> AsyncGenerator[str, None]:
        pipeline = get_trademark_pipeline()
        yield sse_data("__ROUTE__trademark__")
        async for chunk in pipeline.analyze_stream(
            query=request.query,
            nice_classes=request.nice_classes,
            history=history,
        ):
            yield sse_data(chunk)

        yield SSE_DONE


_service: TrademarkService | None = None


def get_trademark_service() -> TrademarkService:
    global _service
    if _service is None:
        _service = TrademarkService()
    return _service
