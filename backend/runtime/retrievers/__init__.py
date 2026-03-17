"""Retriever backends for legal and verdict pipelines."""

from backend.runtime.retrievers.legal_retriever import Neo4jLegalRetriever, RetrievedChunk
from backend.runtime.retrievers.verdict_retriever import Neo4jVerdictRetriever, RetrievedVerdictChunk
from backend.runtime.retrievers.qdrant import (
    QdrantSearchClient,
    LEGAL_COLLECTION,
    VERDICT_COLLECTION,
)

__all__ = [
    "Neo4jLegalRetriever",
    "RetrievedChunk",
    "Neo4jVerdictRetriever",
    "RetrievedVerdictChunk",
    "QdrantSearchClient",
    "LEGAL_COLLECTION",
    "VERDICT_COLLECTION",
]
