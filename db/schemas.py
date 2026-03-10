from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime


# ── Auth ──────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=128)
    confirm_password: str = Field(..., min_length=6, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Mật khẩu xác nhận không khớp")
        return self


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserRead"


class UserRead(BaseModel):
    id: int
    username: str
    is_admin: bool = False
    created_at: datetime

    class Config:
        from_attributes = True



class UsernameChange(BaseModel):
    new_username: str = Field(..., min_length=3, max_length=100)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=128)
    confirm_password: str = Field(..., min_length=6, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Mật khẩu xác nhận không khớp")
        return self


# ── Chat Sessions ────────────────────────────────────

class SessionCreate(BaseModel):
    title: str = "Đoạn chat mới"
    mode: str = "smart"


class SessionRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class SessionRead(BaseModel):
    id: str
    title: str
    mode: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Messages ─────────────────────────────────────────

class MessageCreate(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str
    route_type: Optional[str] = None


class MessageRead(BaseModel):
    id: str
    role: str
    content: str
    route_type: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SessionWithMessages(SessionRead):
    messages: List[MessageRead] = []


# ── Trademark ────────────────────────────────────────

class TrademarkSearchRequest(BaseModel):
    brand_name: str = Field(..., min_length=1, max_length=500, description="Tên nhãn hiệu cần tra cứu")
    nice_classes: Optional[List[str]] = Field(None, description="Lọc theo nhóm Nice")
    limit: int = Field(20, ge=1, le=100, description="Số kết quả tối đa")


class TrademarkResult(BaseModel):
    brand_name: str
    owner_name: str = ""
    owner_country: str = ""
    registration_number: str = ""
    nice_classes: List[str] = []
    ipr_type: str = ""
    country_of_filing: str = ""
    status: str = ""
    status_date: str = ""
    similarity_score: float = 0.0
    match_type: str = ""  # "exact", "fuzzy", "semantic"
    st13: str = ""
    application_number: str = ""
    registration_date: str = ""
    application_date: str = ""
    expiry_date: str = ""
    feature: str = ""
    ip_office: str = ""


class TrademarkSearchResponse(BaseModel):
    success: bool
    query: str
    results: List[TrademarkResult]
    total_found: int
    processing_time_ms: float


class TrademarkAnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500, description="Tên nhãn hiệu cần phân tích xung đột")
    session_id: Optional[str] = Field(None, description="Session ID để load lịch sử hội thoại")
    nice_classes: Optional[List[str]] = Field(None, description="Nhóm Nice để lọc")
