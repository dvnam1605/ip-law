from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Config(BaseSettings):
    APP_NAME: str = "Legal RAG Chatbot API"
    APP_DESCRIPTION: str = "API tu van phap luat Viet Nam su dung RAG voi Neo4j va Gemini AI"
    API_VERSION: str = "2.0.0"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 1605

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/legal_rag"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    JWT_SECRET_KEY: str = "change-me-in-production-use-env-var"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    NEO4J_URI: str = "bolt://127.0.0.1:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    CORS_ORIGIN_REGEX: str = (
        r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?$"
    )
    CORS_ALLOW_CREDENTIALS: bool = True

    TOKEN_CLEANUP_INTERVAL_SECONDS: int = 6 * 3600
    SERVICE_TIMEOUT_SECONDS: int = 90

    TOP_K_RETRIEVAL: int = 5
    TOP_K_VERDICT: int = 8

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            v = value.strip()
            if not v:
                return []
            return [item.strip() for item in v.split(",") if item.strip()]
        return []


config = Config()
