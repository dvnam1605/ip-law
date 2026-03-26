from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.api.routes import query as query_routes
from backend.api.routes import verdict as verdict_routes
from backend.api.routes import trademark as trademark_routes
from backend.api.schemas import QueryResponse, SourceInfo, VerdictQueryResponse, VerdictSourceInfo
from backend.db.schemas import TrademarkSearchResponse, TrademarkResult


class FakeQueryService:
    async def run_query(self, request):
        return QueryResponse(
            success=True,
            query=request.query,
            answer="query-answer",
            sources=[SourceInfo(doc_name="Luat A", score=0.9)],
            retrieved_chunks=1,
            processing_time_ms=10.0,
        )

    async def stream_query(self, request, history):
        yield "data: chunk-1\\n\\n"
        yield "data: [DONE]\\n\\n"

    async def stream_smart_query(self, request, history):
        yield "data: __ROUTE__legal__\\n\\n"
        yield "data: smart-1\\n\\n"
        yield "data: [DONE]\\n\\n"


class FakeVerdictService:
    async def run_query(self, request):
        return VerdictQueryResponse(
            success=True,
            query=request.query,
            answer="verdict-answer",
            sources=[VerdictSourceInfo(case_number="01/2024", score=0.8)],
            retrieved_chunks=1,
            processing_time_ms=12.0,
        )

    async def stream_query(self, request, history):
        yield "data: verdict-1\\n\\n"
        yield "data: [DONE]\\n\\n"


class FakeTrademarkService:
    async def search(self, request):
        return TrademarkSearchResponse(
            success=True,
            query=request.brand_name,
            results=[
                TrademarkResult(
                    brand_name="ABC",
                    owner_name="Owner",
                    owner_country="VN",
                    registration_number="REG-1",
                    nice_classes=["25"],
                    ipr_type="Trademark",
                    country_of_filing="VN",
                    status="active",
                    status_date="2024-01-01",
                    similarity_score=0.95,
                    match_type="exact",
                    st13="st13",
                    application_number="app-1",
                    registration_date="2023-01-01",
                    application_date="2022-01-01",
                    expiry_date="2032-01-01",
                    feature="word",
                    ip_office="VN",
                )
            ],
            total_found=1,
            processing_time_ms=8.0,
        )

    async def stream_analysis(self, request, history):
        yield "data: __ROUTE__trademark__\\n\\n"
        yield "data: tm-1\\n\\n"
        yield "data: [DONE]\\n\\n"


def test_query_route_uses_service_response_model():
    app = FastAPI()
    app.include_router(query_routes.router)
    with patch("backend.api.routes.query.get_query_service", return_value=FakeQueryService()):
        client = TestClient(app)
        res = client.post("/api/query", json={"query": "xin chao"})

    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == "query-answer"
    assert data["retrieved_chunks"] == 1


def test_smart_query_stream_route_emits_route_marker():
    app = FastAPI()
    app.include_router(query_routes.router)
    with patch("backend.api.routes.query.get_query_service", return_value=FakeQueryService()), patch(
        "backend.api.routes.query.load_history", return_value=[]
    ):
        client = TestClient(app)
        res = client.post("/api/smart/query/stream", json={"query": "a", "session_id": "s1"})

    assert res.status_code == 200
    assert "__ROUTE__legal__" in res.text
    assert "[DONE]" in res.text


def test_verdict_route_uses_service_response_model():
    app = FastAPI()
    app.include_router(verdict_routes.router)
    with patch("backend.api.routes.verdict.get_verdict_service", return_value=FakeVerdictService()):
        client = TestClient(app)
        res = client.post("/api/verdict/query", json={"query": "hoi ve ban an"})

    assert res.status_code == 200
    assert res.json()["answer"] == "verdict-answer"


def test_trademark_routes_use_service():
    app = FastAPI()
    app.include_router(trademark_routes.router)
    with patch("backend.api.routes.trademark.get_trademark_service", return_value=FakeTrademarkService()), patch(
        "backend.api.routes.trademark.load_history", return_value=[]
    ):
        client = TestClient(app)
        search_res = client.post("/api/trademark/search", json={"brand_name": "abc", "limit": 10})
        stream_res = client.post("/api/trademark/analyze/stream", json={"query": "abc", "session_id": "s1"})

    assert search_res.status_code == 200
    assert search_res.json()["total_found"] == 1
    assert stream_res.status_code == 200
    assert "__ROUTE__trademark__" in stream_res.text
    assert "[DONE]" in stream_res.text
