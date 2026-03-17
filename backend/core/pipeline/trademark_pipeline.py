"""
Trademark RAG Pipeline
2-tier trademark search (exact → fuzzy via pg_trgm) + Gemini AI conflict analysis.
Uses PostgreSQL with pg_trgm for fuzzy matching.
"""
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
from backend.core.config import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from google import genai
from google.genai import types

from backend.core.pipeline.rag_pipeline import format_history

from sqlalchemy import text, select, func, or_, case, literal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from backend.db.database import DATABASE_URL
from backend.db.models import Trademark, NiceClass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or config.GEMINI_API_KEY
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or config.GEMINI_MODEL


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
    st13: str = ""
    application_number: str = ""
    registration_date: str = ""
    application_date: str = ""
    expiry_date: str = ""
    feature: str = ""
    ip_office: str = ""


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
| Nhãn hiệu | Chủ sở hữu | Số đăng ký | Nhóm Nice | Trạng thái | Ngày hết hạn | Mức giống |

### 3. Đánh giá rủi ro(đánh giá 1 trong 3 mức: Cao / Trung bình / Thấp)
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
    """2-tier trademark retrieval from PostgreSQL (exact + fuzzy via pg_trgm)."""

    def __init__(self):
        self.engine = create_async_engine(DATABASE_URL, echo=False)
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    def close(self):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.engine.dispose())
        except RuntimeError:
            asyncio.run(self.engine.dispose())

    def _row_to_match(self, row: Trademark, score: float, match_type: str) -> TrademarkMatch:
        nice = [nc.class_number for nc in row.nice_classes] if row.nice_classes else []
        return TrademarkMatch(
            brand_name=row.brand_name or "",
            owner_name=row.owner_name or "",
            owner_country=row.owner_country or "",
            registration_number=row.registration_number or "",
            nice_classes=nice,
            ipr_type=row.ipr_type or "",
            country_of_filing=row.country_of_filing or "",
            status=row.status or "",
            status_date=row.status_date or "",
            similarity_score=round(score, 4),
            match_type=match_type,
            st13=row.st13 or "",
            application_number=row.application_number or "",
            registration_date=row.registration_date or "",
            application_date=row.application_date or "",
            expiry_date=row.expiry_date or "",
            feature=row.feature or "",
            ip_office=row.ip_office or "",
        )

    async def search_exact_async(self, brand_name: str, limit: int = 20) -> List[TrademarkMatch]:
        """Tier 1: Exact / CONTAINS match using ILIKE."""
        async with self.session_factory() as session:
            pattern = f"%{brand_name}%"
            query = (
                select(Trademark)
                .where(Trademark.brand_name_lower.ilike(pattern.lower()))
                .order_by(
                    case(
                        (func.lower(Trademark.brand_name) == brand_name.lower(), 0),
                        else_=1,
                    ),
                    Trademark.brand_name,
                )
                .limit(limit)
            )
            result = await session.execute(query)
            rows = result.scalars().all()

        matches = []
        for row in rows:
            is_exact = row.brand_name_lower == brand_name.lower()
            score = 1.0 if is_exact else 0.8
            matches.append(self._row_to_match(row, score, "exact"))
        return matches

    async def search_fuzzy_async(self, brand_name: str, limit: int = 20) -> List[TrademarkMatch]:
        """Tier 2: Fuzzy search using pg_trgm similarity."""
        async with self.session_factory() as session:
            # Use raw SQL for pg_trgm similarity function
            sql = text("""
                SELECT t.id, similarity(t.brand_name_lower, :name) AS sim
                FROM trademarks t
                WHERE similarity(t.brand_name_lower, :name) > 0.15
                ORDER BY sim DESC
                LIMIT :lim
            """)
            result = await session.execute(sql, {"name": brand_name.lower(), "lim": limit})
            sim_rows = result.fetchall()

            if not sim_rows:
                return []

            ids = [r[0] for r in sim_rows]
            sim_map = {r[0]: r[1] for r in sim_rows}

            # Fetch full Trademark objects
            tm_result = await session.execute(
                select(Trademark).where(Trademark.id.in_(ids))
            )
            tm_rows = {t.id: t for t in tm_result.scalars().all()}

        matches = []
        for tid in ids:
            row = tm_rows.get(tid)
            if row:
                score = min(sim_map[tid], 0.95)
                matches.append(self._row_to_match(row, score, "fuzzy"))
        return matches

    async def search_async(
        self,
        brand_name: str,
        nice_classes: List[str] = None,
        limit: int = 20,
    ) -> List[TrademarkMatch]:
        """Combined 2-tier search: exact → fuzzy. Deduplicates by st13/registration_number."""
        exact = await self.search_exact_async(brand_name, limit)
        fuzzy = await self.search_fuzzy_async(brand_name, limit)

        seen = {}
        for match in exact + fuzzy:
            key = match.st13 or match.registration_number
            if not key:
                continue
            if key not in seen or match.similarity_score > seen[key].similarity_score:
                seen[key] = match

        results = sorted(seen.values(), key=lambda m: m.similarity_score, reverse=True)

        if nice_classes:
            nice_set = set(nice_classes)
            results = [
                m for m in results
                if not m.nice_classes or nice_set.intersection(set(m.nice_classes))
            ]

        return results[:limit]

    def search(
        self,
        brand_name: str,
        nice_classes: List[str] = None,
        limit: int = 20,
    ) -> List[TrademarkMatch]:
        """Synchronous wrapper for search_async."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    asyncio.run, self.search_async(brand_name, nice_classes, limit)
                ).result()
        else:
            return asyncio.run(self.search_async(brand_name, nice_classes, limit))


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

    async def search_async(
        self,
        brand_name: str,
        nice_classes: List[str] = None,
        limit: int = 20,
    ) -> List[TrademarkMatch]:
        """Async search — returns matches without AI analysis."""
        return await self.retriever.search_async(brand_name, nice_classes, limit)

    def search(
        self,
        brand_name: str,
        nice_classes: List[str] = None,
        limit: int = 20,
    ) -> List[TrademarkMatch]:
        """Sync search — returns matches without AI analysis."""
        return self.retriever.search(brand_name, nice_classes, limit)

    def _format_context(self, matches: List[TrademarkMatch]) -> str:
        if not matches:
            return "Không tìm thấy nhãn hiệu tương tự nào trong CSDL."

        parts = []
        for i, m in enumerate(matches, 1):
            nice_str = ", ".join(m.nice_classes) if m.nice_classes else "N/A"
            lines = [
                f"[{i}] Nhãn hiệu: {m.brand_name}",
                f"    Chủ sở hữu: {m.owner_name} ({m.owner_country})",
                f"    Số đăng ký: {m.registration_number}",
                f"    Số đơn: {m.application_number}" if m.application_number else None,
                f"    ST13: {m.st13}" if m.st13 else None,
                f"    Nhóm Nice: {nice_str}",
                f"    Loại: {m.ipr_type or m.feature or 'N/A'}",
                f"    Nước đăng ký: {m.country_of_filing or m.ip_office or 'N/A'}",
                f"    Trạng thái: {m.status}",
                f"    Ngày nộp đơn: {m.application_date}" if m.application_date else None,
                f"    Ngày đăng ký: {m.registration_date}" if m.registration_date else None,
                f"    Ngày hết hạn: {m.expiry_date}" if m.expiry_date else None,
                f"    Mức giống: {m.similarity_score:.0%} ({m.match_type})",
            ]
            parts.append("\n".join(line for line in lines if line is not None))
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
        # Retrieve matches (async directly)
        matches = await self.retriever.search_async(query, nice_classes, limit)

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
