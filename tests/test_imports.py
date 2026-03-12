"""
Post-refactor import verification tests.
Run with: python -m pytest tests/test_imports.py -v
"""
import importlib
import pytest


BACKEND_MODULES = [
    "backend",
    "backend.db.database",
    "backend.db.models",
    "backend.db.schemas",
    "backend.db.auth",
    "backend.core.rag_pipeline",
    "backend.core.verdict_rag_pipeline",
    "backend.core.smart_router",
    "backend.core.trademark_pipeline",
    "backend.api.schemas",
    "backend.api.deps",
    "backend.api.app",
    "backend.api.routes.health",
    "backend.api.routes.auth",
    "backend.api.routes.sessions",
    "backend.api.routes.query",
    "backend.api.routes.verdict",
    "backend.api.routes.trademark",
    "backend.api.routes.admin",
    "backend.utils.neo4j_retriever",
    "backend.utils.verdict_neo4j_retriever",
    "backend.utils.trademark_pg_ingest",
    "backend.chunking.legal_chunker",
    "backend.chunking.legal_chunker_v2",
    "backend.chunking.verdict_chunker",
]


@pytest.mark.parametrize("module_name", BACKEND_MODULES)
def test_import(module_name: str):
    """Verify each backend module can be imported without errors."""
    mod = importlib.import_module(module_name)
    assert mod is not None, f"Failed to import {module_name}"


def test_fastapi_app_exists():
    """Verify the FastAPI app can be created."""
    from backend.api.app import app
    assert app is not None
    assert app.title == "Legal RAG Chatbot API"


def test_db_base_has_models():
    """Verify DB models are registered on Base."""
    from backend.db.database import Base
    table_names = set(Base.metadata.tables.keys())
    assert "users" in table_names
    assert "chat_sessions" in table_names
    assert "messages" in table_names
    assert "trademarks" in table_names
