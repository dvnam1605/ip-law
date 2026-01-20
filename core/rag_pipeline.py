import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

import google.generativeai as genai

import sys
sys.path.insert(0, str(PROJECT_ROOT))
from utils.neo4j_retriever import Neo4jLegalRetriever, RetrievedChunk


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EMBEDDING_MODEL_PATH = str(PROJECT_ROOT / "vietnamese_embedding")
TOP_K_RETRIEVAL = int(os.getenv("TOP_K_RETRIEVAL", "5"))


@dataclass
class RAGResponse:
    """Response từ RAG pipeline"""
    answer: str
    sources: List[Dict[str, Any]]
    query: str
    retrieved_chunks: int
    

SYSTEM_PROMPT = """Bạn là chuyên gia tư vấn pháp luật Việt Nam. Trả lời NGẮN GỌN, TỰ NHIÊN như đang nói chuyện với người bình thường.

## CÁCH TRẢ LỜI:

1. **Mở đầu thẳng vấn đề** (2-3 câu): Trả lời trực tiếp câu hỏi, nêu điểm quan trọng nhất.

2. **Nếu cần liệt kê nhiều mức/loại**: Dùng bảng gọn, KHÔNG dùng bullet points dài.

3. **Giải thích thêm** (nếu cần): Tối đa 2-3 ý chính, ngắn gọn.

4. **Kết thúc**: Ghi chú ngắn về nguồn văn bản và nhắc có thể có cập nhật mới.

## QUY TẮC:
- KHÔNG dùng header như "TÓM TẮT", "CHI TIẾT" - viết tự nhiên như đang giải thích
- Chỉ nêu các mức PHỔ BIẾN, bỏ qua chi tiết vụn vặt
- Trích dẫn gọn: "theo Điều X Luật Y (Số: Z)"
- Cuối cùng luôn nhắc: "Lưu ý: Quy định trên theo [văn bản], có thể đã được cập nhật."
"""

CONTEXT_TEMPLATE = """
=== NGUỒN {index} ===
📄 {doc_name} | Số: {doc_number} | Loại: {doc_type}
📍 {dieu} - {dieu_title}
📅 Hiệu lực: {effective_date}

{content}
"""

USER_PROMPT_TEMPLATE = """
CÂU HỎI: {query}

VĂN BẢN PHÁP LUẬT:
{context}

Trả lời tự nhiên, mượt mà như đang giải thích cho người bình thường. Không dùng header cứng nhắc.
"""


class GeminiRAGPipeline:
    """
    RAG Pipeline với Neo4j Retriever và Gemini API
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern để tái sử dụng connection"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(
        self,
        api_key: str = GEMINI_API_KEY,
        model_name: str = GEMINI_MODEL,
        embedding_model_path: str = EMBEDDING_MODEL_PATH,
        top_k: int = TOP_K_RETRIEVAL
    ):
        if self._initialized:
            return
            
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found. Set it in .env file.")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_PROMPT
        )
        
        # Initialize retriever - use absolute path
        self.retriever = Neo4jLegalRetriever(
            embedding_model_path=embedding_model_path
        )
        self.top_k = top_k
        self._initialized = True
        
        print(f"✅ Initialized Gemini RAG Pipeline")
        print(f"   Model: {model_name}")
        print(f"   Top-K: {top_k}")
    
    def _format_context(self, results: List[RetrievedChunk]) -> str:
        """Format retrieved results thành context string"""
        context_parts = []
        
        for i, result in enumerate(results, 1):
            full_content = ""
            if result.context_before:
                full_content += f"[Context trước]\n{result.context_before}\n"
            full_content += result.content
            if result.context_after:
                full_content += f"\n[Context sau]\n{result.context_after}"
            
            context_part = CONTEXT_TEMPLATE.format(
                index=i,
                doc_name=result.doc_name or "N/A",
                doc_type=result.doc_type or "N/A",
                doc_number=result.doc_number or "N/A",
                dieu=result.dieu or "N/A",
                dieu_title=result.dieu_title or "",
                effective_date=result.effective_date or "N/A",
                content=full_content
            )
            context_parts.append(context_part)
        
        return "\n".join(context_parts)
    
    def _extract_sources(self, results: List[RetrievedChunk]) -> List[Dict]:
        """Extract source citations từ results"""
        sources = []
        for r in results:
            sources.append({
                "doc_name": r.doc_name,
                "doc_type": r.doc_type,
                "doc_number": r.doc_number,
                "dieu": r.dieu,
                "dieu_title": r.dieu_title,
                "score": r.score
            })
        return sources
    
    def query(
        self,
        query: str,
        top_k: int = None,
        query_date: str = None,
        doc_types: List[str] = None,
    ) -> RAGResponse:
        """Execute RAG query"""
        k = top_k or self.top_k
        
        results = self.retriever.search(
            query=query,
            top_k=k,
            query_date=query_date,
            doc_types=doc_types,
            expand_context=True,
            context_window=1
        )
        
        if not results:
            return RAGResponse(
                answer="Xin lỗi, tôi không tìm thấy văn bản pháp luật nào liên quan đến câu hỏi của bạn.",
                sources=[],
                query=query,
                retrieved_chunks=0
            )
        
        context = self._format_context(results)
        user_prompt = USER_PROMPT_TEMPLATE.format(query=query, context=context)
        
        response = self.model.generate_content(user_prompt)
        answer = response.text
        
        return RAGResponse(
            answer=answer,
            sources=self._extract_sources(results),
            query=query,
            retrieved_chunks=len(results)
        )
    
    def query_stream(
        self,
        query: str,
        top_k: int = None,
        query_date: str = None,
        doc_types: List[str] = None,
    ):
        """Execute RAG query with streaming response - yields text chunks"""
        from typing import Generator
        
        k = top_k or self.top_k
        
        results = self.retriever.search(
            query=query,
            top_k=k,
            query_date=query_date,
            doc_types=doc_types,
            expand_context=True,
            context_window=1
        )
        
        if not results:
            yield "Xin lỗi, tôi không tìm thấy văn bản pháp luật nào liên quan đến câu hỏi của bạn."
            return
        
        context = self._format_context(results)
        user_prompt = USER_PROMPT_TEMPLATE.format(query=query, context=context)
        
        # Use streaming generation
        response = self.model.generate_content(user_prompt, stream=True)
        
        for chunk in response:
            if chunk.text:
                yield chunk.text
    
    def close(self):
        """Close connections"""
        self.retriever.close()
        GeminiRAGPipeline._instance = None
        self._initialized = False


def get_pipeline() -> GeminiRAGPipeline:
    """Get or create RAG pipeline singleton"""
    return GeminiRAGPipeline()
