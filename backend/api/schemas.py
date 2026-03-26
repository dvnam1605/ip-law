"""
Pydantic request/response schemas for the API layer.
Extracted from the monolithic api/main.py.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional


class SmartQueryRequest(BaseModel):
    query: str = Field(..., description="Câu hỏi pháp luật hoặc tình huống", min_length=1, max_length=5000)
    session_id: Optional[str] = Field(None, description="Session ID để load lịch sử hội thoại")


class QueryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "Điều kiện đăng ký nhãn hiệu ở Việt Nam?",
                "top_k": 5,
                "query_date": "2024-01-01",
                "doc_types": ["Luật", "Nghị định"]
            }
        }
    )

    query: str = Field(..., description="Câu hỏi pháp luật", min_length=5, max_length=1000)
    top_k: Optional[int] = Field(5, ge=1, le=20, description="Số lượng tài liệu tham khảo (1-20)")
    query_date: Optional[str] = Field(None, description="Ngày truy vấn (YYYY-MM-DD)")
    doc_types: Optional[List[str]] = Field(None, description="Lọc theo loại văn bản")
    session_id: Optional[str] = Field(None, description="Session ID để load lịch sử hội thoại")


class SourceInfo(BaseModel):
    doc_name: Optional[str] = None
    doc_type: Optional[str] = None
    doc_number: Optional[str] = None
    dieu: Optional[str] = None
    dieu_title: Optional[str] = None
    score: float


class QueryResponse(BaseModel):
    success: bool
    query: str
    answer: str
    sources: List[SourceInfo]
    retrieved_chunks: int
    processing_time_ms: float


class VerdictQueryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "Tòa xử thế nào khi bị đơn xâm phạm nhãn hiệu?",
                "top_k": 8,
                "ip_types": ["Nhãn hiệu"],
                "trial_level": "Phúc thẩm"
            }
        }
    )

    query: str = Field(..., description="Câu hỏi về tình huống/bản án", min_length=5, max_length=5000)
    top_k: Optional[int] = Field(8, ge=1, le=20, description="Số lượng tài liệu tham khảo (1-20)")
    ip_types: Optional[List[str]] = Field(None, description="Lọc theo loại SHTT")
    trial_level: Optional[str] = Field(None, description="Lọc theo cấp xét xử")
    session_id: Optional[str] = Field(None, description="Session ID để load lịch sử hội thoại")


class VerdictSourceInfo(BaseModel):
    case_number: Optional[str] = None
    court_name: Optional[str] = None
    judgment_date: Optional[str] = None
    dispute_type: Optional[str] = None
    ip_types: Optional[List[str]] = None
    section_type: Optional[str] = None
    score: float


class VerdictQueryResponse(BaseModel):
    success: bool
    query: str
    answer: str
    sources: List[VerdictSourceInfo]
    retrieved_chunks: int
    processing_time_ms: float


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
