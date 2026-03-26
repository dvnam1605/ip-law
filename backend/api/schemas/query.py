from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SmartQueryRequest(BaseModel):
    query: str = Field(..., description="Cau hoi phap luat hoac tinh huong", min_length=1, max_length=5000)
    session_id: Optional[str] = Field(None, description="Session ID de load lich su hoi thoai")


class QueryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "Dieu kien dang ky nhan hieu o Viet Nam?",
                "top_k": 5,
                "query_date": "2024-01-01",
                "doc_types": ["Luat", "Nghi dinh"],
            }
        }
    )

    query: str = Field(..., description="Cau hoi phap luat", min_length=5, max_length=1000)
    top_k: Optional[int] = Field(5, ge=1, le=20, description="So luong tai lieu tham khao (1-20)")
    query_date: Optional[str] = Field(None, description="Ngay truy van (YYYY-MM-DD)")
    doc_types: Optional[List[str]] = Field(None, description="Loc theo loai van ban")
    session_id: Optional[str] = Field(None, description="Session ID de load lich su hoi thoai")


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
