"""Core RAG pipelines package."""

from backend.core.pipeline.rag_pipeline import get_pipeline
from backend.core.pipeline.verdict_rag_pipeline import get_verdict_pipeline
from backend.core.pipeline.trademark_pipeline import get_trademark_pipeline

__all__ = [
    "get_pipeline",
    "get_verdict_pipeline",
    "get_trademark_pipeline",
]
