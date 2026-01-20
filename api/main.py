"""
FastAPI Application for Legal RAG Chatbot
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.rag_pipeline import get_pipeline, RAGResponse


# ============ PYDANTIC MODELS ============
class QueryRequest(BaseModel):
    """Request body for query endpoint"""
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


class SourceInfo(BaseModel):
    """Source citation info"""
    doc_name: Optional[str] = None
    doc_type: Optional[str] = None
    doc_number: Optional[str] = None
    dieu: Optional[str] = None
    dieu_title: Optional[str] = None
    score: float


class QueryResponse(BaseModel):
    """Response for query endpoint"""
    success: bool
    query: str
    answer: str
    sources: List[SourceInfo]
    retrieved_chunks: int
    processing_time_ms: float


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    version: str


# ============ LIFESPAN ============
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler for startup and shutdown"""
    # Startup
    print("🚀 Starting Legal RAG API...")
    try:
        pipeline = get_pipeline()
        print("✅ RAG Pipeline initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize RAG Pipeline: {e}")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down Legal RAG API...")
    try:
        pipeline = get_pipeline()
        pipeline.close()
    except:
        pass


# ============ FASTAPI APP ============
app = FastAPI(
    title="Legal RAG Chatbot API",
    description="API tư vấn pháp luật Việt Nam sử dụng RAG với Neo4j và Gemini AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ ENDPOINTS ============
@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - health check"""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="1.0.0"
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="1.0.0"
    )


@app.post("/api/query", response_model=QueryResponse)
async def query_legal(request: QueryRequest):
    """
    Truy vấn pháp luật
    
    Gửi câu hỏi và nhận câu trả lời từ hệ thống RAG.
    """
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
    """Truy vấn pháp luật (GET method)"""
    request = QueryRequest(query=q, top_k=top_k, query_date=date)
    return await query_legal(request)


@app.post("/api/query/stream")
async def query_legal_stream(request: QueryRequest):
    """
    Truy vấn pháp luật với streaming response (Server-Sent Events)
    
    Response sẽ được trả về từng phần để hiển thị real-time.
    """
    from fastapi.responses import StreamingResponse
    
    async def generate():
        try:
            pipeline = get_pipeline()
            
            # Stream từng chunk từ Gemini
            for chunk in pipeline.query_stream(
                query=request.query,
                top_k=request.top_k,
                query_date=request.query_date,
                doc_types=request.doc_types
            ):
                # Escape newlines để không phá vỡ SSE format
                escaped = chunk.replace('\\', '\\\\').replace('\n', '\\n')
                yield f"data: {escaped}\n\n"
            
            # Signal end of stream
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


# ============ RUN SERVER ============
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=1605,
        reload=True
    )
