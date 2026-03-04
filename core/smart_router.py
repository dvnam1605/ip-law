import re
import os
import sys
from typing import List, Dict, Any, Literal
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from google import genai
from google.genai import types

sys.path.insert(0, str(PROJECT_ROOT))

RouteType = Literal['legal', 'verdict', 'combined']

VERDICT_KEYWORDS = [
    r'tình huống', r'bồi thường', r'khởi kiện', r'kiện', r'phản tố',
    r'tòa\s*(án)?\s*(sẽ|đã|xử|xét)', r'bị đơn', r'nguyên đơn',
    r'bản án', r'án lệ', r'xâm phạm', r'vi phạm.*quyền',
    r'thiệt hại', r'bồi hoàn', r'xin lỗi.*công khai', r'đăng báo',
    r'công ty.*(?:tôi|chúng tôi)', r'tôi\s*(?:phát hiện|muốn|cần|nên)',
    r'nên\s*(?:làm|xử lý|kiện|khởi)', r'hướng giải quyết',
    r'phán quyết', r'nhận định', r'tranh chấp',
    r'sao chép', r'hàng nhái', r'hàng giả',
]

LEGAL_KEYWORDS = [
    r'(?:điều|khoản)\s*\d+', r'quy định', r'luật\s+(?:nào|gì|nói)',
    r'thủ tục', r'điều kiện\s*(?:đăng ký|cấp|bảo hộ)',
    r'thời hạn\s*(?:bảo hộ|đăng ký|khiếu nại)',
    r'nghị định', r'thông tư', r'hướng dẫn',
    r'đối tượng.*bảo hộ', r'quyền.*(?:tác giả|sáng chế|nhãn hiệu)',
    r'đăng ký.*(?:nhãn hiệu|sáng chế|kiểu dáng)',
    r'(?:mức|hình thức).*xử phạt', r'phân biệt.*(?:giữa|và)',
]

# Patterns that signal user wants practical advice (situation + "what should I do?")
# These questions inherently need BOTH legal framework + case-law reference → combined
ADVISORY_PATTERNS = [
    r'(?:tôi|chúng tôi)\s*(?:phát hiện|phát\s*hiện\s*ra).*(?:nên|cần|phải|làm)',
    r'(?:nên|cần|phải)\s*(?:làm\s*(?:gì|thế\s*nào|sao)|xử\s*lý\s*(?:thế\s*nào|ra\s*sao))',
    r'(?:bước|cách)\s*(?:xử\s*lý|giải\s*quyết|khiếu\s*nại|khởi\s*kiện)',
    r'(?:tôi|chúng tôi)\s*(?:bị|đã bị|đang bị).*(?:nên|cần|phải|làm)',
    r'(?:phát hiện|phát\shien).*(?:sử dụng|dùng|copy|sao chép|làm nhái|làm giả)',
    r'(?:xử\s*lý|giải\s*quyết|bảo\s*vệ).*(?:thế\s*nào|như\s*thế\s*nào|ra\s*sao)',
    r'(?:tôi|chúng tôi).*(?:logo|nhãn hiệu|thương hiệu|sáng chế|tác phẩm|thiết kế).*(?:bị|đang)',
    r'(?:bên khác|đối thủ|công ty khác|người khác).*(?:sử dụng|dùng|copy|sao chép|bắt chước)',
]


def classify_query(query: str) -> RouteType:
    q = query.lower()
    verdict_score = sum(1 for p in VERDICT_KEYWORDS if re.search(p, q))
    legal_score = sum(1 for p in LEGAL_KEYWORDS if re.search(p, q))
    advisory_hit = any(re.search(p, q) for p in ADVISORY_PATTERNS)

    # Advisory intent (situation + asking what to do) → always combined
    if advisory_hit and verdict_score >= 1:
        return 'combined'

    if verdict_score >= 2 and legal_score >= 2:
        return 'combined'
    if verdict_score > legal_score and verdict_score >= 2:
        return 'verdict'
    if legal_score > verdict_score and legal_score >= 1:
        return 'legal'
    if verdict_score >= 1:
        return 'combined'
    return 'legal'


COMBINED_SYSTEM_PROMPT = """Bạn là Chuyên gia Pháp lý AI chuyên tư vấn Luật Sở hữu trí tuệ Việt Nam. Bạn có 2 nguồn dữ liệu:
- [VĂN BẢN PHÁP LUẬT]: Các điều luật, nghị định, thông tư hiện hành
- [BẢN ÁN THAM KHẢO]: Các bản án thực tế đã xét xử

## NGUYÊN TẮC TUYỆT ĐỐI:
1. **ZERO HALLUCINATION**: CHỈ trích dẫn điều luật và bản án có trong dữ liệu bên dưới. KHÔNG tự bịa ra bất kỳ số hiệu văn bản, số bản án, hay nội dung nào không có trong nguồn cung cấp.
2. Phân biệt rõ: đâu là quy định pháp luật (nên, phải, được phép) và đâu là thực tiễn xét xử (Tòa đã xử thế nào).
3. Ngôn ngữ thận trọng: "Dựa trên thực tiễn xét xử...", "Theo quy định tại...", "Nhiều khả năng..."
4. Nếu dữ liệu không đủ, thừa nhận giới hạn.

## CÁCH TRẢ LỜI:

1. **Vấn đề pháp lý**: Xác định vấn đề cốt lõi (2-3 câu).

2. **Cơ sở pháp luật**: Trích dẫn các điều luật liên quan từ [VĂN BẢN PHÁP LUẬT]:
   - Quyền của chủ sở hữu, hành vi bị cấm, thủ tục xử lý
   - Trích: "Theo Điều X Luật Y..."

3. **Thực tiễn xét xử**: Đối chiếu với [BẢN ÁN THAM KHẢO] (CHỈ các bản án có trong danh sách):
   - Tòa đã nhận định và phán quyết thế nào trong vụ tương tự
   - Trích: "Theo Bản án số X, Tòa nhận định..."

4. **Tư vấn hướng xử lý**: Kết hợp cả luật và thực tiễn:
   - Các bước nên làm (theo quy trình luật định)
   - Dự đoán kết quả (dựa trên bản án tương tự)
   - Mức bồi thường/xử phạt tham khảo

5. **Kết luận**: Lời khuyên chốt lại + nhắc tham vấn luật sư.
"""


class SmartRouter:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        from core.rag_pipeline import get_pipeline
        from core.verdict_rag_pipeline import get_verdict_pipeline

        self.legal_pipeline = get_pipeline()
        self.verdict_pipeline = get_verdict_pipeline()

        api_key = os.getenv("GEMINI_API_KEY")
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.client = genai.Client(api_key=api_key)
        self.combined_model_name = model_name
        self.combined_system_instruction = COMBINED_SYSTEM_PROMPT
        self._initialized = True
        print("✅ Smart Router ready")

    async def route_and_stream(self, query: str):
        route = classify_query(query)
        yield f"__ROUTE__{route}__"

        if route == 'legal':
            async for chunk in self.legal_pipeline.query_stream(query=query):
                yield chunk
        elif route == 'verdict':
            async for chunk in self.verdict_pipeline.query_stream(query=query):
                yield chunk
        else:
            async for chunk in self._combined_stream(query):
                yield chunk

    async def _combined_stream(self, query: str):
        import asyncio
        
        legal_ctx = None
        verdict_ctx = None
        verdict_results = None

        def fetch_legal():
            nonlocal legal_ctx
            results = self.legal_pipeline.retriever.search(
                query=query, top_k=5, expand_context=True, context_window=1
            )
            if results:
                legal_ctx = self.legal_pipeline._format_context(results)

        def fetch_verdict():
            nonlocal verdict_ctx, verdict_results
            results = self.verdict_pipeline._retrieve(query, top_k=8, ip_types=None, trial_level=None)
            if results:
                verdict_results = results
                verdict_ctx = self.verdict_pipeline._format_context(results)

        await asyncio.gather(
            asyncio.to_thread(fetch_legal),
            asyncio.to_thread(fetch_verdict),
        )

        if not legal_ctx and not verdict_ctx:
            yield "Xin lỗi, tôi không tìm thấy dữ liệu liên quan trong cơ sở dữ liệu."
            return

        context_parts = []
        if legal_ctx:
            context_parts.append(f"[VĂN BẢN PHÁP LUẬT]:\n{legal_ctx}")
        if verdict_ctx:
            case_list = self.verdict_pipeline._case_list(verdict_results) if verdict_results else ""
            context_parts.append(
                f"[BẢN ÁN THAM KHẢO] (CHỈ các bản án sau được phép trích dẫn: {case_list}):\n{verdict_ctx}"
            )

        prompt = f"""
CÂU HỎI: {query}

{chr(10).join(context_parts)}

NHẮC LẠI: CHỈ trích dẫn điều luật và bản án có trong dữ liệu trên. KHÔNG nhắc đến bất kỳ nguồn nào khác.
Hãy tư vấn toàn diện, kết hợp cả quy định pháp luật lẫn thực tiễn xét xử.
"""
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

    def close(self):
        SmartRouter._instance = None
        self._initialized = False


def get_smart_router() -> SmartRouter:
    return SmartRouter()
