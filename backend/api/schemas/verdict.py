from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class VerdictQueryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "Toa xu the nao khi bi don xam pham nhan hieu?",
                "top_k": 8,
                "ip_types": ["Nhan hieu"],
                "trial_level": "Phuc tham",
            }
        }
    )

    query: str = Field(..., description="Cau hoi ve tinh huong/ban an", min_length=5, max_length=5000)
    top_k: Optional[int] = Field(8, ge=1, le=20, description="So luong tai lieu tham khao (1-20)")
    ip_types: Optional[List[str]] = Field(None, description="Loc theo loai SHTT")
    trial_level: Optional[str] = Field(None, description="Loc theo cap xet xu")
    session_id: Optional[str] = Field(None, description="Session ID de load lich su hoi thoai")


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
