from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.rag_pipeline import get_pipeline, RAGResponse
from core.verdict_rag_pipeline import get_verdict_pipeline, VerdictRAGResponse
from core.smart_router import get_smart_router


class SmartQueryRequest(BaseModel):
    query: str = Field(..., description="Câu hỏi pháp luật hoặc tình huống", min_length=5, max_length=5000)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Legal RAG API...")
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
    
    yield
    
    print("🛑 Shutting down Legal RAG API...")
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


app = FastAPI(
    title="Legal RAG Chatbot API",
    description="API tư vấn pháp luật Việt Nam sử dụng RAG với Neo4j và Gemini AI",
    version="1.0.0",
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


@app.get("/", response_model=HealthResponse)
async def root():
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="1.0.0"
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        version="1.0.0"
    )


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
    
    async def generate():
        try:
            pipeline = get_pipeline()
            
            for chunk in pipeline.query_stream(
                query=request.query,
                top_k=request.top_k,
                query_date=request.query_date,
                doc_types=request.doc_types
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
    
    async def generate():
        try:
            pipeline = get_verdict_pipeline()
            
            for chunk in pipeline.query_stream(
                query=request.query,
                top_k=request.top_k,
                ip_types=request.ip_types,
                trial_level=request.trial_level
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

    async def generate():
        try:
            router = get_smart_router()
            for chunk in router.route_and_stream(query=request.query):
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=1605,
        reload=True
    )
