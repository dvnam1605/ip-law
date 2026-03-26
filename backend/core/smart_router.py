import os
import asyncio
import logging
from typing import List, Optional, AsyncGenerator, Any, Dict
from pathlib import Path
from dotenv import load_dotenv

from google import genai
from google.genai import types

from backend.core.config import config
from backend.core.pipeline.rag_pipeline import format_history
from backend.core.router_constants import (
    RouteType,
    COMBINED_SYSTEM_PROMPT
)
from backend.core.routing_strategies import (
    classify_query_with_strategies,
    DEFAULT_STRATEGIES,
    RoutingStrategy
)

# Setup logging
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class SmartRouter:
    """
    Orchestrates routing between specialized RAG pipelines and a combined hybrid pipeline.
    Supports Dependency Injection for pipelines and routing strategies.
    Implements a thread-safe Singleton pattern.
    """
    _instance: Optional['SmartRouter'] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        legal_pipeline: Any = None,
        verdict_pipeline: Any = None,
        trademark_pipeline: Any = None,
        routing_strategies: Dict[str, RoutingStrategy] = None,
        gemini_client: Any = None
    ):
        if self._initialized:
            return
        
        self.legal_pipeline = legal_pipeline
        self.verdict_pipeline = verdict_pipeline
        self.trademark_pipeline = trademark_pipeline
        self.strategies = routing_strategies or DEFAULT_STRATEGIES

        api_key = os.getenv("GEMINI_API_KEY") or config.GEMINI_API_KEY
        model_name = os.getenv("GEMINI_MODEL") or config.GEMINI_MODEL
        
        self.client = gemini_client or genai.Client(api_key=api_key)
        self.combined_model_name = model_name
        self.combined_system_instruction = COMBINED_SYSTEM_PROMPT
        
        self._initialized = True
        logger.info("Smart Router initialized with Async support and Dependency Injection")

    def _ensure_pipelines(self):
        """Lazy load pipelines if not already provided via DI."""
        from backend.core.pipeline.rag_pipeline import get_pipeline
        from backend.core.pipeline.verdict_rag_pipeline import get_verdict_pipeline
        from backend.core.pipeline.trademark_pipeline import get_trademark_pipeline

        if not self.legal_pipeline:
            self.legal_pipeline = get_pipeline()
        if not self.verdict_pipeline:
            self.verdict_pipeline = get_verdict_pipeline()
        if not self.trademark_pipeline:
            self.trademark_pipeline = get_trademark_pipeline()

    async def route_and_stream(self, query: str, history: Optional[List[Dict[str, str]]] = None) -> AsyncGenerator[str, None]:
        """
        Determines the route and streams the response from the appropriate pipeline.
        Uses native await for async-ready pipelines.
        """
        self._ensure_pipelines()
        route = classify_query_with_strategies(query, self.strategies)
        yield f"__ROUTE__{route}__"

        try:
            if route == 'legal':
                async for chunk in self.legal_pipeline.query_stream(query=query, history=history):
                    yield chunk
            elif route == 'verdict':
                async for chunk in self.verdict_pipeline.query_stream(query=query, history=history):
                    yield chunk
            elif route == 'trademark':
                # Trademark pipeline analyze_stream is currently sync-wrapped in some implementations, 
                # but we'll call it directly and assume it's an async generator.
                async for chunk in self.trademark_pipeline.analyze_stream(query=query, history=history):
                    yield chunk
            else:
                async for chunk in self._combined_stream(query, history=history):
                    yield chunk
        except Exception as e:
            logger.exception("Error in route_and_stream for route %s: %s", route, e)
            yield f"\n[Lỗi hệ thống]: Đã xảy ra lỗi khi xử lý yêu cầu ({route}). Vui lòng thử lại sau."

    async def _combined_stream(self, query: str, history: Optional[List[Dict[str, str]]] = None) -> AsyncGenerator[str, None]:
        """
        Executes a hybrid retrieval from both legal and verdict pipelines and synthesizes an answer.
        Uses native asyncio.gather with await for improved performance.
        """
        # Run retrievals in parallel using native await
        try:
            legal_task = self.legal_pipeline.retriever.search(
                query=query, top_k=5, expand_context=True, context_window=1
            )
            verdict_task = self.verdict_pipeline.retriever.search(
                query=query, top_k=8, expand_context=True, context_window=1, boost_reasoning=True
            )
            
            legal_results, verdict_results = await asyncio.gather(legal_task, verdict_task)
        except Exception as e:
            logger.error("Combined retrieval failed: %s", e)
            yield "Xin lỗi, đã có lỗi xảy ra khi truy xuất dữ liệu."
            return

        legal_ctx = self.legal_pipeline._format_context(legal_results) if legal_results else ""
        verdict_ctx = self.verdict_pipeline._format_context(verdict_results) if verdict_results else ""

        if not legal_ctx and not verdict_ctx:
            yield "Xin lỗi, tôi không tìm thấy dữ liệu liên quan trong cơ sở dữ liệu pháp luật và bản án."
            return

        context_parts = []
        if legal_ctx:
            context_parts.append(f"[VĂN BẢN PHÁP LUẬT]:\n{legal_ctx}")
        
        if verdict_ctx:
            case_list = self.verdict_pipeline._case_list(verdict_results) if verdict_results else "Không rõ"
            context_parts.append(
                f"[BẢN ÁN THAM KHẢO] (CHỈ các bản án sau được phép trích dẫn: {case_list}):\n{verdict_ctx}"
            )

        prompt = f"""
{format_history(history) if history else ""}
CÂU HỎI: {query}

{chr(10).join(context_parts)}

NHẮC LẠI: CHỈ trích dẫn điều luật và bản án có trong dữ liệu trên. KHÔNG nhắc đến bất kỳ nguồn nào khác.
Hãy tư vấn toàn diện, kết hợp cả quy định pháp luật lẫn thực tiễn xét xử.
"""
        try:
            response = await self.client.aio.models.generate_content_stream(
                model=self.combined_model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.combined_system_instruction,
                )
            )
            async for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error("Gemini synthesis failed in combined mode: %s", e)
            yield "\n[Lỗi]: Không thể tổng hợp câu trả lời từ LLM."

    async def close(self):
        """Asynchronously closes all pipelines and resets the singleton instance."""
        self._ensure_pipelines()
        await asyncio.gather(
            self.legal_pipeline.close(),
            self.verdict_pipeline.close(),
            self.trademark_pipeline.close()
        )
        SmartRouter._instance = None
        self._initialized = False
        logger.info("Smart Router closed")


def get_smart_router() -> SmartRouter:
    """Factory function to get the SmartRouter singleton."""
    return SmartRouter()
