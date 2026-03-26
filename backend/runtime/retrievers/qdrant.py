"""
Shared Qdrant search client for dense retrieval.
Used by neo4j_retriever and verdict_neo4j_retriever to perform
vector search via Qdrant, then map results back to Neo4j for full context.
"""
import os
import asyncio
from typing import List, Tuple, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny

from sentence_transformers import SentenceTransformer


QDRANT_URL = os.getenv("QDRANT_URL", "http://192.168.1.199:6333")
LEGAL_COLLECTION = os.getenv("QDRANT_LEGAL_COLLECTION", "legal_chunks")
VERDICT_COLLECTION = os.getenv("QDRANT_VERDICT_COLLECTION", "verdict_chunks")


class QdrantSearchClient:
    """Async Qdrant vector search client for dense RAG retrieval."""

    def __init__(self, url: str = None, embedding_model_path: str = None):
        self.url = url or QDRANT_URL
        self.client = AsyncQdrantClient(url=self.url)

        self.embedding_model = None
        if embedding_model_path and os.path.exists(embedding_model_path):
            print(f"Loading embedding model from {embedding_model_path}...")
            self.embedding_model = SentenceTransformer(embedding_model_path)
            dim = self.embedding_model.get_sentence_embedding_dimension()
            print(f"Model loaded. Dimension: {dim}")

    async def encode(self, query: str) -> List[float]:
        """Encodes a query string into a vector. Non-blocking via to_thread."""
        if not self.embedding_model:
            raise ValueError("Embedding model not loaded")
        # Run CPU-bound encoding in a thread to avoid blocking the event loop
        embedding = await asyncio.to_thread(self.embedding_model.encode, query)
        return embedding.tolist()

    async def search(
        self,
        collection: str,
        query_embedding: List[float],
        id_field: str = "chunk_id",
        candidate_ids: List[str] = None,
        top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        """
        Search Qdrant for similar vectors asynchronously.

        Args:
            collection: Qdrant collection name
            query_embedding: Query vector
            id_field: Payload field name for chunk ID (chunk_id or vchunk_id)
            candidate_ids: Optional list of valid IDs to filter (from Neo4j pre-filter)
            top_k: Number of results

        Returns:
            List of (chunk_id, score) tuples, sorted by score desc
        """
        query_filter = None
        if candidate_ids:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key=id_field,
                        match=MatchAny(any=candidate_ids)
                    )
                ]
            )

        results = await self.client.query_points(
            collection_name=collection,
            query=query_embedding,
            query_filter=query_filter,
            limit=top_k,
            with_payload=[id_field],
        )

        return [(hit.payload[id_field], hit.score) for hit in results.points]

    async def close(self):
        await self.client.close()
