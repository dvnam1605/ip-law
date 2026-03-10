import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.rag_pipeline import get_pipeline, RAGResponse
from core.verdict_rag_pipeline import get_verdict_pipeline, VerdictRAGResponse
from core.smart_router import get_smart_router
from core.trademark_pipeline import get_trademark_pipeline

from db.database import get_db, init_db, async_session_factory
from db.models import User, ChatSession, Message
from db.schemas import (
    UserCreate, UserLogin, TokenResponse, UserRead,
    UsernameChange, PasswordChange,
    SessionCreate, SessionRename, SessionRead,
    MessageCreate, MessageRead, SessionWithMessages,
    TrademarkSearchRequest, TrademarkResult, TrademarkSearchResponse,
    TrademarkAnalyzeRequest,
)
from db.auth import (
    hash_password, verify_password, create_access_token, get_current_user,
    blacklist_token, cleanup_expired_tokens, get_current_admin_user,
)


# ═══════════════════════════════════════════════════════
#  Pydantic models (existing RAG stuff)
# ═══════════════════════════════════════════════════════

class SmartQueryRequest(BaseModel):
    query: str = Field(..., description="Câu hỏi pháp luật hoặc tình huống", min_length=5, max_length=5000)
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


# ═══════════════════════════════════════════════════════
#  App lifecycle
# ═══════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Legal RAG API...")

    # Init database tables
    try:
        await init_db()
        print("✅ PostgreSQL tables initialized")
    except Exception as e:
        print(f"❌ Failed to initialize PostgreSQL: {e}")

    try:
        pipeline = get_pipeline()
        print("✅ Legal RAG Pipeline initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize Legal RAG Pipeline: {e}")

    try:
        verdict_pipeline = get_verdict_pipeline()
        print("✅ Verdict RAG Pipeline initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize Verdict RAG Pipeline: {e}")

    try:
        trademark_pipeline = get_trademark_pipeline()
        print("✅ Trademark Pipeline initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize Trademark Pipeline: {e}")

    # Background task: cleanup expired blacklisted tokens every 6 hours
    async def token_cleanup_loop():
        while True:
            try:
                await asyncio.sleep(6 * 3600)  # 6 hours
                async with async_session_factory() as db:
                    count = await cleanup_expired_tokens(db)
                    if count:
                        print(f"🧹 Cleaned up {count} expired blacklisted tokens")
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ Token cleanup error: {e}")

    cleanup_task = asyncio.create_task(token_cleanup_loop())

    yield

    print("🛑 Shutting down Legal RAG API...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        pipeline = get_pipeline()
        pipeline.close()
    except:
        pass
    try:
        verdict_pipeline = get_verdict_pipeline()
        verdict_pipeline.close()
    except:
        pass
    try:
        trademark_pipeline = get_trademark_pipeline()
        trademark_pipeline.close()
    except:
        pass


app = FastAPI(
    title="Legal RAG Chatbot API",
    description="API tư vấn pháp luật Việt Nam sử dụng RAG với Neo4j và Gemini AI",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════
#  Health
# ═══════════════════════════════════════════════════════

@app.get("/", response_model=HealthResponse)
async def root():
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="2.0.0"
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="2.0.0"
    )


# ═══════════════════════════════════════════════════════
#  Auth endpoints
# ═══════════════════════════════════════════════════════

@app.post("/api/auth/register", response_model=TokenResponse)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if username exists
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")

    user = User(
        username=data.username,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.flush()  # get user.id
    await db.refresh(user)

    token = create_access_token(user.id, user.username)
    return TokenResponse(
        access_token=token,
        user=UserRead.model_validate(user),
    )


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")

    token = create_access_token(user.id, user.username)
    return TokenResponse(
        access_token=token,
        user=UserRead.model_validate(user),
    )


@app.get("/api/auth/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)):
    return UserRead.model_validate(current_user)


@app.post("/api/auth/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: AsyncSession = Depends(get_db),
):
    """Blacklist the current token so it can no longer be used."""
    await blacklist_token(credentials.credentials, db)
    return {"detail": "Đã đăng xuất thành công"}


@app.patch("/api/auth/username", response_model=UserRead)
async def change_username(
    data: UsernameChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check if new username already taken
    result = await db.execute(select(User).where(User.username == data.new_username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")

    current_user.username = data.new_username
    await db.flush()
    await db.refresh(current_user)
    return UserRead.model_validate(current_user)


@app.patch("/api/auth/password")
async def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")

    current_user.hashed_password = hash_password(data.new_password)
    await db.flush()
    return {"detail": "Đổi mật khẩu thành công"}


# ═══════════════════════════════════════════════════════
#  Chat Session endpoints
# ═══════════════════════════════════════════════════════

@app.get("/api/sessions", response_model=List[SessionRead])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.asc())
    )
    return [SessionRead.model_validate(s) for s in result.scalars().all()]


@app.post("/api/sessions", response_model=SessionRead)
async def create_session(
    data: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = ChatSession(
        user_id=current_user.id,
        title=data.title,
        mode=data.mode,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return SessionRead.model_validate(session)


@app.patch("/api/sessions/{session_id}", response_model=SessionRead)
async def rename_session(
    session_id: str,
    data: SessionRename,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    session.title = data.title
    await db.flush()
    await db.refresh(session)
    return SessionRead.model_validate(session)


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    await db.delete(session)
    return {"detail": "Đã xóa session"}


@app.get("/api/sessions/{session_id}/messages", response_model=List[MessageRead])
async def get_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify ownership
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    return [MessageRead.model_validate(m) for m in result.scalars().all()]


@app.post("/api/sessions/{session_id}/messages", response_model=MessageRead)
async def add_message(
    session_id: str,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify ownership
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    msg = Message(
        session_id=session_id,
        role=data.role,
        content=data.content,
        route_type=data.route_type,
    )
    db.add(msg)

    # Auto-rename session on first user message
    if data.role == "user" and session.title == "Đoạn chat mới":
        session.title = data.content[:30] + ("..." if len(data.content) > 30 else "")

    await db.flush()
    await db.refresh(msg)
    return MessageRead.model_validate(msg)


# ═══════════════════════════════════════════════════════
#  RAG query endpoints (unchanged logic)
# ═══════════════════════════════════════════════════════


async def _load_history(session_id: Optional[str], limit: int = 5) -> list:
    """Load last N messages from a session for conversation context."""
    if not session_id:
        return []
    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            messages = result.scalars().all()
            # Reverse to chronological order and return as dicts
            return [
                {"role": m.role, "content": m.content}
                for m in reversed(messages)
            ]
    except Exception as e:
        print(f"⚠️ Failed to load history: {e}")
        return []

@app.post("/api/query", response_model=QueryResponse)
async def query_legal(request: QueryRequest):

    start_time = datetime.now()

    try:
        pipeline = get_pipeline()

        result = pipeline.query(
            query=request.query,
            top_k=request.top_k,
            query_date=request.query_date,
            doc_types=request.doc_types
        )

        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        sources = [SourceInfo(**s) for s in result.sources]

        return QueryResponse(
            success=True,
            query=result.query,
            answer=result.answer,
            sources=sources,
            retrieved_chunks=result.retrieved_chunks,
            processing_time_ms=round(processing_time, 2)
        )

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "processing_time_ms": round(processing_time, 2)
            }
        )


@app.get("/api/query", response_model=QueryResponse)
async def query_legal_get(
    q: str = Query(..., description="Câu hỏi pháp luật", min_length=5),
    top_k: int = Query(5, ge=1, le=20, description="Số lượng tài liệu"),
    date: Optional[str] = Query(None, description="Ngày truy vấn (YYYY-MM-DD)")
):
    request = QueryRequest(query=q, top_k=top_k, query_date=date)
    return await query_legal(request)


@app.post("/api/query/stream")
async def query_legal_stream(request: QueryRequest):
    from fastapi.responses import StreamingResponse

    history = await _load_history(request.session_id)

    async def generate():
        try:
            pipeline = get_pipeline()

            async for chunk in pipeline.query_stream(
                query=request.query,
                top_k=request.top_k,
                query_date=request.query_date,
                doc_types=request.doc_types,
                history=history,
            ):
                escaped = chunk.replace('\\', '\\\\').replace('\n', '\\n')
                yield f"data: {escaped}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: [ERROR]{str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/verdict/query", response_model=VerdictQueryResponse)
async def query_verdict(request: VerdictQueryRequest):
    start_time = datetime.now()

    try:
        pipeline = get_verdict_pipeline()

        result = pipeline.query(
            query=request.query,
            top_k=request.top_k,
            ip_types=request.ip_types,
            trial_level=request.trial_level
        )

        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        sources = [VerdictSourceInfo(**s) for s in result.sources]

        return VerdictQueryResponse(
            success=True,
            query=result.query,
            answer=result.answer,
            sources=sources,
            retrieved_chunks=result.retrieved_chunks,
            processing_time_ms=round(processing_time, 2)
        )

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "processing_time_ms": round(processing_time, 2)
            }
        )


@app.get("/api/verdict/query", response_model=VerdictQueryResponse)
async def query_verdict_get(
    q: str = Query(..., description="Câu hỏi về tình huống/bản án", min_length=5),
    top_k: int = Query(8, ge=1, le=20, description="Số lượng tài liệu")
):
    request = VerdictQueryRequest(query=q, top_k=top_k)
    return await query_verdict(request)


@app.post("/api/verdict/query/stream")
async def query_verdict_stream(request: VerdictQueryRequest):
    from fastapi.responses import StreamingResponse

    history = await _load_history(request.session_id)

    async def generate():
        try:
            pipeline = get_verdict_pipeline()

            async for chunk in pipeline.query_stream(
                query=request.query,
                top_k=request.top_k,
                ip_types=request.ip_types,
                trial_level=request.trial_level,
                history=history,
            ):
                escaped = chunk.replace('\\', '\\\\').replace('\n', '\\n')
                yield f"data: {escaped}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: [ERROR]{str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/smart/query/stream")
async def smart_query_stream(request: SmartQueryRequest):
    from fastapi.responses import StreamingResponse

    history = await _load_history(request.session_id)

    async def generate():
        try:
            router = get_smart_router()
            async for chunk in router.route_and_stream(query=request.query, history=history):
                escaped = chunk.replace('\\', '\\\\').replace('\n', '\\n')
                yield f"data: {escaped}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR]{str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ═══════════════════════════════════════════════════════
#  Trademark endpoints
# ═══════════════════════════════════════════════════════

@app.post("/api/trademark/search", response_model=TrademarkSearchResponse)
async def trademark_search(request: TrademarkSearchRequest):
    start_time = datetime.now()
    try:
        pipeline = get_trademark_pipeline()
        matches = await pipeline.search_async(
            brand_name=request.brand_name,
            nice_classes=request.nice_classes,
            limit=request.limit,
        )
        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        results = [
            TrademarkResult(
                brand_name=m.brand_name,
                owner_name=m.owner_name,
                owner_country=m.owner_country,
                registration_number=m.registration_number,
                nice_classes=m.nice_classes,
                ipr_type=m.ipr_type,
                country_of_filing=m.country_of_filing,
                status=m.status,
                status_date=m.status_date,
                similarity_score=m.similarity_score,
                match_type=m.match_type,
                st13=m.st13,
                application_number=m.application_number,
                registration_date=m.registration_date,
                application_date=m.application_date,
                expiry_date=m.expiry_date,
                feature=m.feature,
                ip_office=m.ip_office,
            )
            for m in matches
        ]

        return TrademarkSearchResponse(
            success=True,
            query=request.brand_name,
            results=results,
            total_found=len(results),
            processing_time_ms=round(processing_time, 2),
        )
    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "processing_time_ms": round(processing_time, 2)}
        )


@app.post("/api/trademark/analyze/stream")
async def trademark_analyze_stream(request: TrademarkAnalyzeRequest):
    from fastapi.responses import StreamingResponse

    history = await _load_history(request.session_id)

    async def generate():
        try:
            pipeline = get_trademark_pipeline()
            yield f"data: __ROUTE__trademark__\n\n"
            async for chunk in pipeline.analyze_stream(
                query=request.query,
                nice_classes=request.nice_classes,
                history=history,
            ):
                escaped = chunk.replace('\\', '\\\\').replace('\n', '\\n')
                yield f"data: {escaped}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR]{str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ═══════════════════════════════════════════════════════
#  Admin endpoints
# ═══════════════════════════════════════════════════════

@app.get("/api/admin/stats")
async def get_admin_stats(
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    from db.models import ChatSession, Trademark

    # Lấy tổng số liệu
    total_users_result = await db.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar() or 0

    total_trademarks_result = await db.execute(select(func.count(Trademark.id)))
    total_trademarks = total_trademarks_result.scalar() or 0

    total_sessions_result = await db.execute(select(func.count(ChatSession.id)))
    total_sessions = total_sessions_result.scalar() or 0

    # Mock count cho bộ luật và án lệ từ Neo4j (vì neo4j không query được dễ dàng từ đây)
    total_laws = 1420 
    total_precedents = 70

    # Cung cấp dữ liệu theo thời gian (giả lập 7 ngày gần nhất dựa trên thực tế sẽ group by date)
    # Vì SQLite/Postgres date functions khác nhau, ta sẽ gom đơn giản hoặc trả về mock
    # Để an toàn đa nền tảng, trả về mảng 7 ngày gần đây với số liệu ngẫu nhiên hoặc tính toán thật:
    import random
    from datetime import timedelta
    
    today = datetime.now()
    visits_data = []
    users_data = []
    
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        visits_data.append({"date": d, "visits": random.randint(10, 50)})
        users_data.append({"date": d, "new_users": random.randint(1, 5)})

    return {
        "success": True,
        "totals": {
            "users": total_users,
            "trademarks": total_trademarks,
            "visits": total_sessions,
            "laws": total_laws,
            "precedents": total_precedents,
        },
        "charts": {
            "visits_over_time": visits_data,
            "users_over_time": users_data,
        }
    }


@app.get("/api/admin/users")
async def get_admin_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select, func
    from db.models import User
    
    # Query tổng số User
    total_result = await db.execute(select(func.count(User.id)))
    total = total_result.scalar() or 0
    
    # Query phân trang
    stmt = select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    return {
        "success": True,
        "total": total,
        "data": [
            {
                "id": u.id,
                "username": u.username,
                "is_admin": u.is_admin,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ]
    }


@app.get("/api/admin/sessions")
async def get_admin_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select, func
    from db.models import ChatSession
    from sqlalchemy.orm import selectinload
    
    # Lấy tổng session
    total_result = await db.execute(select(func.count(ChatSession.id)))
    total = total_result.scalar() or 0
    
    # Lấy session kèm User information
    stmt = (select(ChatSession)
            .options(selectinload(ChatSession.user))
            .order_by(ChatSession.created_at.desc())
            .offset(skip)
            .limit(limit))
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    
    return {
        "success": True,
        "total": total,
        "data": [
            {
                "id": s.id,
                "title": s.title,
                "mode": s.mode,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "username": s.user.username if s.user else "Unknown"
            }
            for s in sessions
        ]
    }
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=1605,
        reload=True
    )
