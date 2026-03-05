import os
import sys
from typing import List, Dict, Any
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from google import genai
from google.genai import types

sys.path.insert(0, str(PROJECT_ROOT))
from utils.verdict_neo4j_retriever import Neo4jVerdictRetriever, RetrievedVerdictChunk
from core.rag_pipeline import format_history

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EMBEDDING_MODEL_PATH = str(PROJECT_ROOT / "vietnamese_embedding")
TOP_K = int(os.getenv("TOP_K_VERDICT", "8"))

NO_RESULT_MSG = (
    "Xin lỗi, tôi không tìm thấy bản án nào liên quan đến tình huống "
    "của bạn trong cơ sở dữ liệu."
)

SYSTEM_PROMPT = """Bạn là một Chuyên gia Pháp lý AI chuyên tư vấn Luật Sở hữu trí tuệ Việt Nam. Nhiệm vụ của bạn là giải quyết tình huống pháp lý của người dùng [USER_CASE] bằng cách đối chiếu và áp dụng các nguyên tắc xét xử từ các bản án cũ [PRECEDENT_CONTEXT].

## NGUYÊN TẮC CỐT LÕI (TUYỆT ĐỐI TUÂN THỦ)

1. **ZERO HALLUCINATION (QUAN TRỌNG NHẤT)**:
   - CHỈ ĐƯỢC trích dẫn các bản án có trong [PRECEDENT_CONTEXT] bên dưới. TUYỆT ĐỐI KHÔNG tự bịa ra, thêm vào, hoặc trích dẫn BẤT KỲ bản án/số hiệu/vụ việc nào KHÔNG xuất hiện trong [PRECEDENT_CONTEXT].
   - Nếu bạn "biết" một bản án từ kiến thức training nhưng nó KHÔNG có trong [PRECEDENT_CONTEXT], bạn KHÔNG ĐƯỢC nhắc đến nó.
   - Trước khi trích dẫn "Theo Bản án số X...", hãy kiểm tra: số bản án X có xuất hiện trong [PRECEDENT_CONTEXT] không? Nếu KHÔNG → KHÔNG trích dẫn.
   - Vi phạm quy tắc này là lỗi nghiêm trọng nhất.

2. **Nền tảng suy luận (Rule of Law)**: PHẢI dựa trên cách Tòa án đã nhận định và quyết định trong [PRECEDENT_CONTEXT] để làm cơ sở pháp lý. Tuyệt đối không tự bịa ra luật hoặc dùng kiến thức bên ngoài nếu nó mâu thuẫn với [PRECEDENT_CONTEXT].

3. **Phân tích Tương đồng (Fact-Matching)**: Chỉ ra điểm giống và khác nhau giữa tình huống người dùng và tình tiết trong bản án cũ. Ví dụ: "Tương tự như vụ án số X, tình huống của bạn cũng liên quan đến..."

4. **Áp dụng và Dự phóng (Application)**: Rút ra nguyên tắc giải quyết từ bản án cũ và áp dụng vào tình huống mới. Ví dụ: nếu bản án cũ dùng "giá trị hợp đồng chuyển giao thực tế" để tính bồi thường, hãy khuyên người dùng cung cấp các hợp đồng tương tự.

5. **Ngôn ngữ thận trọng**: Không bao giờ khẳng định 100% kết quả. Dùng: "Dựa trên thực tiễn xét xử...", "Nhiều khả năng Tòa án sẽ xem xét...", "Bạn có thể lập luận theo hướng..."

6. **Giới hạn Ảo giác**: Nếu tình huống chứa yếu tố KHÔNG xuất hiện hoặc không thể suy luận từ [PRECEDENT_CONTEXT], phải thừa nhận: "Bản án tham khảo hiện tại không đề cập đến tình tiết này, nên tôi chưa đủ cơ sở để tư vấn sâu hơn về điểm [X]."

## ĐỊNH DẠNG ĐẦU RA (CẤU TRÚC IRAC)

1. **Vấn đề pháp lý (Issue)**: Tóm tắt vấn đề người dùng đang vướng mắc, xác định loại tranh chấp sở hữu trí tuệ.

2. **Cơ sở tham chiếu (Rule)**: Trích dẫn cách Tòa án đã xử lý trường hợp tương tự TRONG [PRECEDENT_CONTEXT]:
   - Tóm tắt tình tiết liên quan
   - Nhận định pháp lý: luận điểm chính, điều luật áp dụng
   - Phán quyết cụ thể: bồi thường bao nhiêu, biện pháp xử lý
   - Trích dẫn: "Theo Bản án số X, Tòa nhận định rằng..." (CHỈ số bản án có trong context)
   - Nếu nhiều bản án trong context, SO SÁNH cách xử lý và rút ra xu hướng xét xử

3. **Áp dụng tình huống (Application)**: Tư vấn cụ thể cho [USER_CASE]:
   - Điểm giống/khác giữa tình huống và bản án
   - Hướng giải quyết đề xuất (khởi kiện, thương lượng, yêu cầu bồi thường...)
   - Mức bồi thường/xử phạt có thể tham khảo
   - Đề xuất hành động tiếp theo

4. **Kết luận (Conclusion)**: Lời khuyên chốt lại + lưu ý nên tham vấn luật sư chuyên ngành sở hữu trí tuệ cho trường hợp cụ thể.

## QUY TẮC BỔ SUNG:
- Giải thích thuật ngữ pháp lý bằng ngôn ngữ dễ hiểu
- Nêu cụ thể: số tiền, thời hạn, biện pháp, điều luật khi có
- Đọc KỸ toàn bộ [PRECEDENT_CONTEXT] trước khi trả lời, bao gồm phần nhận định và phán quyết
"""

SECTION_LABELS = {
    'header': 'Thông tin vụ án',
    'fact': 'Tình tiết vụ án',
    'lower_court_decision': 'Bản án sơ thẩm',
    'reasoning': 'Nhận định pháp lý',
    'decision_item': 'Phán quyết',
    'court_fee': 'Án phí',
}

CONTEXT_TEMPLATE = """
=== BẢN ÁN {index} ===
Số: {case_number} | Tòa: {court_name} | Ngày: {judgment_date} | Cấp: {trial_level}
Loại sở hữu trí tuệ: {ip_types}
Nguyên đơn: {plaintiff} | Bị đơn: {defendant}
Phần: {section_label}{section_detail}

{content}
"""

USER_PROMPT_TEMPLATE = """
[USER_CASE]: {query}

[PRECEDENT_CONTEXT] (CHỈ các bản án sau đây được phép trích dẫn: {case_list}):
{context}

NHẮC LẠI: CHỈ trích dẫn các bản án có trong [PRECEDENT_CONTEXT] ở trên. KHÔNG được nhắc đến bất kỳ bản án nào khác.
Hãy phân tích và tư vấn cho người dùng theo cấu trúc IRAC. Đối chiếu trực tiếp tình huống với các bản án, đưa ra hướng xử lý cụ thể.
"""


@dataclass
class VerdictRAGResponse:
    answer: str
    sources: List[Dict[str, Any]]
    query: str
    retrieved_chunks: int


class VerdictRAGPipeline:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        api_key=GEMINI_API_KEY,
        model_name=GEMINI_MODEL,
        embedding_model_path=EMBEDDING_MODEL_PATH,
        top_k=TOP_K,
    ):
        if self._initialized:
            return
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .env")

        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.system_instruction = SYSTEM_PROMPT
        self.retriever = Neo4jVerdictRetriever(embedding_model_path=embedding_model_path)
        self.top_k = top_k
        self._initialized = True
        print(f"✅ Verdict RAG Pipeline ready (model={model_name}, top_k={top_k})")

    def _retrieve(self, query, top_k, ip_types, trial_level):
        return self.retriever.search(
            query=query,
            top_k=top_k or self.top_k,
            ip_types=ip_types,
            trial_level=trial_level,
            expand_context=True,
            context_window=1,
            boost_reasoning=True,
        )

    def _section_detail(self, result: RetrievedVerdictChunk) -> str:
        if result.point_number:
            return f" | Luận điểm {result.point_number}"
        if result.party_role:
            return f" | {result.party_role}"
        if result.item_number:
            return f" | Khoản {result.item_number}"
        return ""

    def _build_content(self, result: RetrievedVerdictChunk) -> str:
        parts = []
        if result.context_before:
            parts.append(f"[Context trước]\n{result.context_before}")
        parts.append(result.content)
        if result.context_after:
            parts.append(f"[Context sau]\n{result.context_after}")
        return "\n".join(parts)

    def _format_context(self, results: List[RetrievedVerdictChunk]) -> str:
        parts = []
        for i, r in enumerate(results, 1):
            ip_str = ", ".join(r.ip_types) if isinstance(r.ip_types, list) else str(r.ip_types)
            parts.append(CONTEXT_TEMPLATE.format(
                index=i,
                case_number=r.case_number or "N/A",
                court_name=r.court_name or "N/A",
                judgment_date=r.judgment_date or "N/A",
                trial_level=r.trial_level or "N/A",
                ip_types=ip_str,
                plaintiff=r.plaintiff or "N/A",
                defendant=r.defendant or "N/A",
                section_label=SECTION_LABELS.get(r.section_type, r.section_type),
                section_detail=self._section_detail(r),
                content=self._build_content(r),
            ))
        return "\n".join(parts)

    def _case_list(self, results: List[RetrievedVerdictChunk]) -> str:
        seen = []
        for r in results:
            if r.case_number and r.case_number not in seen:
                seen.append(r.case_number)
        return ", ".join(seen) if seen else "không rõ"

    def _extract_sources(self, results: List[RetrievedVerdictChunk]) -> List[Dict]:
        return [
            {
                "case_number": r.case_number,
                "court_name": r.court_name,
                "judgment_date": r.judgment_date,
                "dispute_type": r.dispute_type,
                "ip_types": r.ip_types if isinstance(r.ip_types, list) else [],
                "section_type": r.section_type,
                "score": round(r.score, 4),
            }
            for r in results
        ]

    def query(self, query, top_k=None, ip_types=None, trial_level=None):
        results = self._retrieve(query, top_k, ip_types, trial_level)
        if not results:
            return VerdictRAGResponse(answer=NO_RESULT_MSG, sources=[], query=query, retrieved_chunks=0)

        prompt = USER_PROMPT_TEMPLATE.format(
            query=query,
            context=self._format_context(results),
            case_list=self._case_list(results),
        )
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instruction,
            )
        )
        answer = response.text
        return VerdictRAGResponse(
            answer=answer,
            sources=self._extract_sources(results),
            query=query,
            retrieved_chunks=len(results),
        )

    async def query_stream(self, query, top_k=None, ip_types=None, trial_level=None, history=None):
        import asyncio
        
        results = await asyncio.to_thread(
            self._retrieve, query, top_k, ip_types, trial_level
        )
        if not results:
            yield NO_RESULT_MSG
            return

        history_text = format_history(history) if history else ""
        prompt = f"{history_text}\n{USER_PROMPT_TEMPLATE.format(query=query, context=self._format_context(results), case_list=self._case_list(results))}"
        response = await self.client.aio.models.generate_content_stream(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instruction,
            )
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text

    def close(self):
        self.retriever.close()
        VerdictRAGPipeline._instance = None
        self._initialized = False


def get_verdict_pipeline() -> VerdictRAGPipeline:
    return VerdictRAGPipeline()
