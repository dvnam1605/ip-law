import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from backend.api.schemas import QueryRequest, SmartQueryRequest, VerdictQueryRequest
from backend.db.schemas import TrademarkAnalyzeRequest, TrademarkSearchRequest
from backend.services.legal import QueryService
from backend.services.verdict import VerdictService
from backend.services.trademark import TrademarkService


async def _collect_async(gen):
    return [item async for item in gen]


def test_query_service_run_query():
    class FakePipeline:
        def query(self, **kwargs):
            return SimpleNamespace(
                query=kwargs["query"],
                answer="ok",
                sources=[{"doc_name": "Luat A", "score": 0.9}],
                retrieved_chunks=2,
            )

    async def _run():
        service = QueryService()
        req = QueryRequest(query="xin chao", top_k=3)
        with patch("backend.services.legal.service.get_pipeline", return_value=FakePipeline()):
            result = await service.run_query(req)
        assert result.success is True
        assert result.query == "xin chao"
        assert result.answer == "ok"
        assert result.retrieved_chunks == 2

    asyncio.run(_run())


def test_query_service_stream_smart_query_sse_format():
    class FakeRouter:
        async def route_and_stream(self, query, history):
            yield "__ROUTE__legal__"
            yield "dong 1\ndong 2"

    async def _run():
        service = QueryService()
        req = SmartQueryRequest(query="a")
        with patch("backend.services.legal.service.get_smart_router", return_value=FakeRouter()):
            chunks = await _collect_async(service.stream_smart_query(req, []))

        assert chunks[0] == "data: __ROUTE__legal__\n\n"
        assert chunks[1].startswith("data: ")
        assert "\\n" in chunks[1]
        assert chunks[-1] == "data: [DONE]\n\n"

    asyncio.run(_run())


def test_verdict_service_run_query():
    class FakePipeline:
        def query(self, **kwargs):
            return SimpleNamespace(
                query=kwargs["query"],
                answer="verdict-ok",
                sources=[{"case_number": "01/2024", "score": 0.8}],
                retrieved_chunks=1,
            )

    async def _run():
        service = VerdictService()
        req = VerdictQueryRequest(query="hoi ve ban an", top_k=4)
        with patch("backend.services.verdict.service.get_verdict_pipeline", return_value=FakePipeline()):
            result = await service.run_query(req)
        assert result.success is True
        assert result.answer == "verdict-ok"
        assert result.retrieved_chunks == 1

    asyncio.run(_run())


def test_trademark_service_search_and_stream():
    fake_match = SimpleNamespace(
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

    class FakePipeline:
        async def search_async(self, **kwargs):
            return [fake_match]

        async def analyze_stream(self, **kwargs):
            yield "phan tich 1"
            yield "phan tich 2"

    async def _run():
        service = TrademarkService()
        req = TrademarkSearchRequest(brand_name="ABC", limit=10)

        with patch("backend.services.trademark.service.get_trademark_pipeline", return_value=FakePipeline()):
            search_result = await service.search(req)
            stream = await _collect_async(
                service.stream_analysis(TrademarkAnalyzeRequest(query="abc", session_id="s1"), [])
            )

        assert search_result.success is True
        assert search_result.total_found == 1
        assert stream[0] == "data: __ROUTE__trademark__\n\n"
        assert stream[-1] == "data: [DONE]\n\n"

    asyncio.run(_run())
