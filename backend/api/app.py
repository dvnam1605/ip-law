"""
FastAPI application entry point.
Registers all route modules and manages app lifecycle.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import config
from backend.core.logging import setup_logging
from backend.core.pipeline.rag_pipeline import get_pipeline
from backend.core.pipeline.verdict_rag_pipeline import get_verdict_pipeline
from backend.core.pipeline.trademark_pipeline import get_trademark_pipeline
from backend.db.database import init_db, async_session_factory
from backend.db.auth import cleanup_expired_tokens

from backend.api.routes import health, auth, sessions, query, verdict, trademark, admin


logger = logging.getLogger(__name__)


def _validate_runtime_config() -> None:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is required but not configured")
    if config.JWT_SECRET_KEY in {
        "change-me-in-production-use-env-var",
        "change-this-secret-key-in-production",
    }:
        raise RuntimeError("JWT_SECRET_KEY must be set to a strong secret")
    if config.CORS_ALLOW_CREDENTIALS and "*" in config.CORS_ORIGINS:
        raise RuntimeError("CORS_ORIGINS cannot contain '*' when credentials are enabled")
    if config.CORS_ALLOW_CREDENTIALS and config.CORS_ORIGIN_REGEX.strip() in {".*", "^.*$"}:
        raise RuntimeError("CORS_ORIGIN_REGEX is too broad when credentials are enabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting Legal RAG API")

    _validate_runtime_config()

    legal_pipeline = None
    verdict_pipeline = None
    trademark_pipeline = None

    await init_db()
    logger.info("PostgreSQL tables initialized")

    legal_pipeline = get_pipeline()
    logger.info("Legal RAG Pipeline initialized")

    verdict_pipeline = get_verdict_pipeline()
    logger.info("Verdict RAG Pipeline initialized")

    trademark_pipeline = get_trademark_pipeline()
    logger.info("Trademark Pipeline initialized")

    # Background task: cleanup expired blacklisted tokens every 6 hours
    async def token_cleanup_loop():
        while True:
            try:
                await asyncio.sleep(config.TOKEN_CLEANUP_INTERVAL_SECONDS)
                async with async_session_factory() as db:
                    count = await cleanup_expired_tokens(db)
                    if count:
                        logger.info("Cleaned up %s expired blacklisted tokens", count)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Token cleanup error: %s", e)

    cleanup_task = asyncio.create_task(token_cleanup_loop())

    yield

    logger.info("Shutting down Legal RAG API")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    
    # SmartRouter singleton close
    try:
        from backend.core.smart_router import get_smart_router
        router = get_smart_router()
        await router.close()
    except Exception:
        logger.exception("Failed to close smart router")

    if legal_pipeline is not None:
        try:
            await legal_pipeline.close()
        except Exception:
            logger.exception("Failed to close legal pipeline")
    if verdict_pipeline is not None:
        try:
            await verdict_pipeline.close()
        except Exception:
            logger.exception("Failed to close verdict pipeline")
    if trademark_pipeline is not None:
        try:
            await trademark_pipeline.close()
        except Exception:
            logger.exception("Failed to close trademark pipeline")


app = FastAPI(
    title=config.APP_NAME,
    description=config.APP_DESCRIPTION,
    version=config.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Unexpected server error. Please try again later."},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=config.CORS_ORIGIN_REGEX,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
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
    backend_root = str(Path(__file__).resolve().parents[1])
    uvicorn.run(
        "backend.api.app:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=True,
        reload_dirs=[backend_root],
    )
