"""
Trademark RAG Pipeline
3-tier trademark search (exact → fuzzy → semantic) + Gemini AI conflict analysis.
"""
import os
import sys
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from google import genai
from google.genai import types

sys.path.insert(0, str(PROJECT_ROOT))
from core.rag_pipeline import format_history

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EMBEDDING_MODEL_PATH = str(PROJECT_ROOT / "vietnamese_embedding")


@dataclass
class TrademarkMatch:
    brand_name: str
    owner_name: str
    owner_country: str
    registration_number: str
    nice_classes: List[str]
    ipr_type: str
    country_of_filing: str
    status: str
    status_date: str
    similarity_score: float
    match_type: str  # "exact", "fuzzy", "semantic"


TRADEMARK_SYSTEM_PROMPT = """Bạn là Chuyên gia Nhãn hiệu AI chuyên phân tích xung đột nhãn hiệu tại Việt Nam.

## NHIỆM VỤ:
Khi người dùng nhập tên nhãn hiệu, bạn phải:
1. Phân tích kết quả tra cứu từ CSDL nhãn hiệu đã đăng ký
2. Đánh giá mức độ xung đột (Cao/Trung bình/Thấp)
3. Tư vấn khả năng đăng ký

## CÁCH PHÂN TÍCH:

### 1. Tổng quan kết quả
- Số lượng nhãn hiệu tương tự tìm được
- Phân loại theo mức độ giống nhau (trùng hoàn toàn / gần giống / tương tự ngữ nghĩa)

### 2. Phân tích chi tiết từng nhãn hiệu xung đột
Trình bày dạng **bảng** gồm các cột:
| Nhãn hiệu | Chủ sở hữu | Số đăng ký | Nhóm Nice | Trạng thái | Mức giống |

### 3. Đánh giá rủi ro
- **🔴 Rủi ro CAO**: Trùng hoặc gần trùng tên + cùng nhóm Nice → gần như không đăng ký được
- **🟡 Rủi ro TRUNG BÌNH**: Tên tương tự nhưng khác nhóm Nice → có thể đăng ký nhưng cần cân nhắc
- **🟢 Rủi ro THẤP**: Chỉ tương tự về ngữ nghĩa → khả năng đăng ký cao

### 4. Khuyến nghị
- Kết luận về khả năng đăng ký
- Gợi ý điều chỉnh nếu rủi ro cao
- Nhắc tham vấn luật sư nếu phức tạp

## QUY TẮC:
- CHỈ phân tích dữ liệu từ kết quả tra cứu bên dưới. KHÔNG bịa thêm nhãn hiệu.
- Nếu không tìm thấy nhãn hiệu tương tự → báo rằng khả năng đăng ký cao nhưng cần kiểm tra thêm.
- Luôn nhắc: kết quả chỉ mang tính tham khảo, cần tra cứu chính thức tại Cục SHTT.
"""

TRADEMARK_PROMPT_TEMPLATE = """
CÂU HỎI: Phân tích xung đột cho nhãn hiệu "{query}"

KẾT QUẢ TRA CỨU TỪ CSDL NHÃN HIỆU ĐÃ ĐĂNG KÝ:
{context}

Hãy phân tích chi tiết mức độ xung đột và đưa ra khuyến nghị.
"""


class TrademarkRetriever:
    """3-tier trademark retrieval from Neo4j."""

    def __init__(
        self,
        uri: str = None,
        user: str = None,
        password: str = None,
        embedding_model_path: str = None,
    ):
        if not NEO4J_AVAILABLE:
            raise ImportError("neo4j required")

        self.uri = uri or os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "aa")

        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

        # Embedding model (shared with other pipelines)
        self.embedding_model = None
        model_path = embedding_model_path or EMBEDDING_MODEL_PATH
        if ST_AVAILABLE and Path(model_path).exists():
            self.embedding_model = SentenceTransformer(model_path)
            self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()

    def close(self):
        self.driver.close()

    def _run_query(self, query: str, params: Dict = None) -> List[Dict]:
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def encode_query(self, text: str) -> List[float]:
        if not self.embedding_model:
            raise ValueError("Embedding model not loaded")
        return self.embedding_model.encode(text).tolist()

    def search_exact(self, brand_name: str, limit: int = 20) -> List[TrademarkMatch]:
        """Tier 1: Exact / CONTAINS match on brand_name."""
        results = self._run_query("""
            MATCH (t:Trademark)
            WHERE toLower(t.brand_name) CONTAINS toLower($name)
            RETURN t {.*} AS trademark
            ORDER BY
                CASE WHEN toLower(t.brand_name) = toLower($name) THEN 0 ELSE 1 END,
                t.brand_name
            LIMIT $limit
        """, {"name": brand_name, "limit": limit})

        matches = []
        for r in results:
            t = r["trademark"]
            name_lower = t.get("brand_name", "").lower()
            query_lower = brand_name.lower()
            # Score: 1.0 for exact, 0.8 for contains
            score = 1.0 if name_lower == query_lower else 0.8
            matches.append(self._to_match(t, score, "exact"))
        return matches

    def search_fuzzy(self, brand_name: str, limit: int = 20) -> List[TrademarkMatch]:
        """Tier 2: Full-text fuzzy search using Neo4j fulltext index."""
        # Use fulltext index with fuzzy operator (~)
        fuzzy_query = f"{brand_name}~"
        try:
            results = self._run_query("""
                CALL db.index.fulltext.queryNodes('trademark_brand_name_fulltext', $query)
                YIELD node, score
                RETURN node {.*} AS trademark, score
                ORDER BY score DESC
                LIMIT $limit
            """, {"query": fuzzy_query, "limit": limit})
        except Exception:
            # Fallback if fulltext index doesn't exist
            return []

        matches = []
        for r in results:
            t = r["trademark"]
            # Normalize score to 0-1 range (fulltext scores can be > 1)
            score = min(r["score"] / 5.0, 0.9)
            matches.append(self._to_match(t, score, "fuzzy"))
        return matches

    def search_semantic(self, brand_name: str, limit: int = 20) -> List[TrademarkMatch]:
        """Tier 3: Vector similarity search using embeddings."""
        if not self.embedding_model:
            return []

        query_embedding = self.encode_query(brand_name)

        try:
            results = self._run_query("""
                CALL db.index.vector.queryNodes('trademark_embedding', $limit, $embedding)
                YIELD node, score
                RETURN node {.*} AS trademark, score
                ORDER BY score DESC
                LIMIT $limit
            """, {"embedding": query_embedding, "limit": limit})
        except Exception:
            return []

        matches = []
        for r in results:
            t = r["trademark"]
            score = r["score"]
            matches.append(self._to_match(t, score, "semantic"))
        return matches

    def search(
        self,
        brand_name: str,
        nice_classes: List[str] = None,
        limit: int = 20,
    ) -> List[TrademarkMatch]:
        """
        Combined 3-tier search: exact → fuzzy → semantic.
        Deduplicates by registration_number, keeps highest score.
        """
        # Run all tiers
        exact = self.search_exact(brand_name, limit)
        fuzzy = self.search_fuzzy(brand_name, limit)
        semantic = self.search_semantic(brand_name, limit)

        # Merge & dedup
        seen = {}
        for match in exact + fuzzy + semantic:
            key = match.registration_number
            if key not in seen or match.similarity_score > seen[key].similarity_score:
                seen[key] = match

        results = sorted(seen.values(), key=lambda m: m.similarity_score, reverse=True)

        # Filter by Nice class if specified
        if nice_classes:
            nice_set = set(nice_classes)
            results = [
                m for m in results
                if not m.nice_classes or nice_set.intersection(set(m.nice_classes))
            ]

        return results[:limit]

    def _to_match(self, t: Dict, score: float, match_type: str) -> TrademarkMatch:
        return TrademarkMatch(
            brand_name=t.get("brand_name", ""),
            owner_name=t.get("owner_name", ""),
            owner_country=t.get("owner_country", ""),
            registration_number=t.get("registration_number", ""),
            nice_classes=t.get("nice_classes", []),
            ipr_type=t.get("ipr_type", ""),
            country_of_filing=t.get("country_of_filing", ""),
            status=t.get("status", ""),
            status_date=t.get("status_date", ""),
            similarity_score=round(score, 4),
            match_type=match_type,
        )


class TrademarkPipeline:
    """Singleton pipeline for trademark search + AI analysis."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        api_key = GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")

        self.client = genai.Client(api_key=api_key)
        self.model_name = GEMINI_MODEL
        self.system_prompt = TRADEMARK_SYSTEM_PROMPT

        self.retriever = TrademarkRetriever()
        self._initialized = True
        print("✅ Trademark Pipeline ready")

    def search(
        self,
        brand_name: str,
        nice_classes: List[str] = None,
        limit: int = 20,
    ) -> List[TrademarkMatch]:
        """Plain search — returns matches without AI analysis."""
        return self.retriever.search(brand_name, nice_classes, limit)

    def _format_context(self, matches: List[TrademarkMatch]) -> str:
        if not matches:
            return "Không tìm thấy nhãn hiệu tương tự nào trong CSDL."

        parts = []
        for i, m in enumerate(matches, 1):
            nice_str = ", ".join(m.nice_classes) if m.nice_classes else "N/A"
            parts.append(
                f"[{i}] Nhãn hiệu: {m.brand_name}\n"
                f"    Chủ sở hữu: {m.owner_name} ({m.owner_country})\n"
                f"    Số đăng ký: {m.registration_number}\n"
                f"    Nhóm Nice: {nice_str}\n"
                f"    Loại: {m.ipr_type}\n"
                f"    Nước đăng ký: {m.country_of_filing}\n"
                f"    Trạng thái: {m.status}\n"
                f"    Mức giống: {m.similarity_score:.0%} ({m.match_type})"
            )
        return "\n\n".join(parts)

    async def analyze_stream(
        self,
        query: str,
        nice_classes: List[str] = None,
        limit: int = 20,
        history: List[Dict] = None,
    ):
        """
        SSE-compatible streaming: search trademarks + AI analysis.
        Yields text chunks for streaming response.
        """
        import asyncio

        # Retrieve matches (blocking → offload to thread)
        matches = await asyncio.to_thread(
            self.retriever.search, query, nice_classes, limit
        )

        context = self._format_context(matches)
        history_text = format_history(history) if history else ""

        prompt = f"{history_text}\n{TRADEMARK_PROMPT_TEMPLATE.format(query=query, context=context)}"

        response = await self.client.aio.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt,
            ),
        )

        async for chunk in response:
            if chunk.text:
                yield chunk.text

    def close(self):
        self.retriever.close()
        TrademarkPipeline._instance = None
        self._initialized = False


def get_trademark_pipeline() -> TrademarkPipeline:
    return TrademarkPipeline()
