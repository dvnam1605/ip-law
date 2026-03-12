"""Trademark search and analysis endpoints."""
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.db.schemas import (
    TrademarkSearchRequest, TrademarkResult, TrademarkSearchResponse,
    TrademarkAnalyzeRequest,
)
from backend.api.deps import load_history
from backend.core.trademark_pipeline import get_trademark_pipeline

router = APIRouter(prefix="/api/trademark", tags=["Trademark"])


@router.post("/search", response_model=TrademarkSearchResponse)
async def trademark_search(request: TrademarkSearchRequest):
    start_time = datetime.now()
    try:
        pipeline = get_trademark_pipeline()
        matches = await pipeline.search_async(
            brand_name=request.brand_name,
            nice_classes=request.nice_classes,
            limit=request.limit,
        )
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
    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "processing_time_ms": round(processing_time, 2)}
        )


@router.post("/analyze/stream")
async def trademark_analyze_stream(request: TrademarkAnalyzeRequest):
    history = await load_history(request.session_id)

    async def generate():
        try:
            pipeline = get_trademark_pipeline()
            yield f"data: __ROUTE__trademark__\n\n"
            async for chunk in pipeline.analyze_stream(
                query=request.query,
                nice_classes=request.nice_classes,
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
