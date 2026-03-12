"""
FastAPI application entry point.
Registers all route modules and manages app lifecycle.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.rag_pipeline import get_pipeline
from backend.core.verdict_rag_pipeline import get_verdict_pipeline
from backend.core.trademark_pipeline import get_trademark_pipeline
from backend.db.database import init_db, async_session_factory
from backend.db.auth import cleanup_expired_tokens

from backend.api.routes import health, auth, sessions, query, verdict, trademark, admin


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
                await asyncio.sleep(6 * 3600)
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

# ── Register routers ────────────────────────────────────
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(query.router)
app.include_router(verdict.router)
app.include_router(trademark.router)
app.include_router(admin.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.api.app:app",
        host="0.0.0.0",
        port=1605,
        reload=True,
    )
