import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from backend.core.config import config

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

from backend.runtime.retrievers.qdrant import QdrantSearchClient, LEGAL_COLLECTION


@dataclass
class RetrievedChunk:
    chunk_id: str
    content: str
    score: float
    dieu: Optional[str]
    dieu_title: Optional[str]
    chuong: Optional[str]
    doc_name: str
    doc_number: str
    doc_type: str
    effective_date: Optional[str]
    context_before: Optional[str] = None
    context_after: Optional[str] = None


class Neo4jLegalRetriever:
    """
    Dense Retrieval Flow:
    1. Neo4j Cypher filter: văn bản đang có hiệu lực
    2. Qdrant vector search trên tập đã lọc
    3. Neo4j NEXT để lấy đủ context
    """

    def __init__(
        self,
        uri: str = None,
        user: str = None,
        password: str = None,
        embedding_model_path: str = None,
        qdrant_url: str = None,
    ):
        if not NEO4J_AVAILABLE:
            raise ImportError("neo4j package required: pip install neo4j")

        self.uri = uri or os.getenv("NEO4J_URI") or config.NEO4J_URI
        self.user = user or os.getenv("NEO4J_USER") or config.NEO4J_USER
        self.password = password or os.getenv("NEO4J_PASSWORD") or config.NEO4J_PASSWORD

        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

        # Qdrant client for vector search
        self.qdrant = QdrantSearchClient(
            url=qdrant_url,
            embedding_model_path=embedding_model_path
        )
        # For backward compat check in search()
        self.embedding_model = self.qdrant.embedding_model
        self.collection_name = os.getenv("QDRANT_LEGAL_COLLECTION", LEGAL_COLLECTION)

        # Project-wide setting: dense-only retrieval.
        self.use_neo4j_prefilter = (os.getenv("LEGAL_PREFILTER_NEO4J", "0").strip().lower() in {"1", "true", "yes", "on"})

    def close(self):
        self.driver.close()
        self.qdrant.close()

    def _run_query(self, query: str, params: Dict = None) -> List[Dict]:
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def encode_query(self, query: str) -> List[float]:
        return self.qdrant.encode(query)

    def search(
        self,
        query: str,
        query_date: str = None,
        doc_types: List[str] = None,
        status: str = "active",
        top_k: int = 10,
        expand_context: bool = True,
        context_window: int = 1,
    ) -> List[RetrievedChunk]:
        candidates = None
        if self.use_neo4j_prefilter:
            if query_date is None:
                query_date = datetime.now().strftime("%Y-%m-%d")
            candidates = self._filter_by_validity(query_date, doc_types, status)
            if not candidates:
                print("⚠️ No valid documents found for the given criteria")
                return []
            print(f"📋 Found {len(candidates)} candidate chunks after filtering")

        ranked = self._vector_search_ranked(query, candidates, top_k=top_k)

        results = self._hydrate_chunks(ranked, top_k=top_k)

        if expand_context and results:
            results = self._expand_context(results, context_window)

        return results

    def search_ids(
        self,
        query: str,
        query_date: str = None,
        doc_types: List[str] = None,
        status: str = "active",
        top_k: int = 10,
    ) -> List[str]:
        """Benchmark-friendly retrieval: return ranked IDs directly from retrieval stage.

        This intentionally skips Neo4j hydration/context expansion so benchmark metrics
        evaluate pure retrieval quality.
        """
        candidates = None
        print(self.use_neo4j_prefilter)
        if self.use_neo4j_prefilter:
            if query_date is None:
                query_date = datetime.now().strftime("%Y-%m-%d")
            candidates = self._filter_by_validity(query_date, doc_types, status)
            if not candidates:
                return []

        ranked = self._vector_search_ranked(query, candidates, top_k=top_k)

        return [cid for cid, _ in ranked[:top_k]]

    def _filter_by_validity(
        self,
        query_date: str,
        doc_types: List[str] = None,
        status: str = "active",
    ) -> List[str]:

        conditions = ["d.status = $status"]
        params = {"status": status, "query_date": query_date}

        conditions.append("(d.effective_date IS NULL OR d.effective_date <= $query_date)")

        if doc_types:
            conditions.append("d.doc_type IN $doc_types")
            params["doc_types"] = doc_types

        where_clause = " AND ".join(conditions)

        query = f"""
        MATCH (c:Chunk)-[:PART_OF]->(d:Document)
        WHERE {where_clause}
        RETURN c.chunk_id AS chunk_id
        """

        results = self._run_query(query, params)
        return [r["chunk_id"] for r in results]

    def _vector_search_ranked(
        self,
        query: str,
        candidate_ids: List[str],
        top_k: int,
    ) -> List[Tuple[str, float]]:
        """Dense vector search via Qdrant."""
        if not self.embedding_model:
            return []

        query_embedding = self.qdrant.encode(query)

        try:
            return self.qdrant.search(
                collection=self.collection_name,
                query_embedding=query_embedding,
                id_field="chunk_id",
                candidate_ids=candidate_ids,
                top_k=top_k,
            )
        except Exception as e:
            print(f"⚠️ Qdrant search failed: {e}")
            return []

    def _hydrate_chunks(
        self,
        ranked_chunk_ids: List[Tuple[str, float]],
        top_k: int,
    ) -> List[RetrievedChunk]:
        """Fetch full chunk/document metadata from Neo4j preserving ranked order."""
        if not ranked_chunk_ids:
            return []

        chunk_ids = [cid for cid, _ in ranked_chunk_ids[:top_k]]
        score_map = {cid: score for cid, score in ranked_chunk_ids}

        cypher = """
        UNWIND $chunk_ids AS cid
        MATCH (c:Chunk {chunk_id: cid})-[:PART_OF]->(d:Document)
        RETURN
            c.chunk_id AS chunk_id,
            c.content AS content,
            c.dieu AS dieu,
            c.dieu_title AS dieu_title,
            c.chuong AS chuong,
            d.doc_name AS doc_name,
            d.doc_number AS doc_number,
            d.doc_type AS doc_type,
            d.effective_date AS effective_date
        """
        rows = self._run_query(cypher, {"chunk_ids": chunk_ids})
        row_map = {r["chunk_id"]: r for r in rows if r.get("chunk_id")}

        hydrated: List[RetrievedChunk] = []
        for cid in chunk_ids:
            r = row_map.get(cid)
            if not r:
                continue
            hydrated.append(
                RetrievedChunk(
                    chunk_id=r["chunk_id"],
                    content=r["content"],
                    score=score_map.get(r["chunk_id"], 0),
                    dieu=r["dieu"],
                    dieu_title=r["dieu_title"],
                    chuong=r["chuong"],
                    doc_name=r["doc_name"],
                    doc_number=r["doc_number"],
                    doc_type=r["doc_type"],
                    effective_date=str(r["effective_date"]) if r["effective_date"] else None,
                )
            )

        return hydrated

    def _vector_search(
        self,
        query: str,
        candidate_ids: List[str],
        top_k: int,
    ) -> List[RetrievedChunk]:
        """Backward-compatible wrapper for callers expecting hydrated chunks."""
        ranked = self._vector_search_ranked(query, candidate_ids, top_k)
        return self._hydrate_chunks(ranked, top_k)

    def _expand_context(
        self,
        results: List[RetrievedChunk],
        context_window: int = 1,
    ) -> List[RetrievedChunk]:
        chunk_ids = [r.chunk_id for r in results]

        cypher_query = f"""
        UNWIND $chunk_ids AS cid
        MATCH (c:Chunk {{chunk_id: cid}})
        OPTIONAL MATCH (prev)-[:NEXT*1..{context_window}]->(c)
        WITH c, collect(prev.content) AS prev_contents
        OPTIONAL MATCH (c)-[:NEXT*1..{context_window}]->(next)
        WITH c, prev_contents, collect(next.content) AS next_contents
        RETURN
            c.chunk_id AS chunk_id,
            CASE WHEN size(prev_contents) > 0
                 THEN reduce(s = '', x IN prev_contents | s + x + '\\n---\\n')
                 ELSE null END AS context_before,
            CASE WHEN size(next_contents) > 0
                 THEN reduce(s = '', x IN next_contents | s + x + '\\n---\\n')
                 ELSE null END AS context_after
        """

        context_results = self._run_query(cypher_query, {"chunk_ids": chunk_ids})
        context_map = {r["chunk_id"]: r for r in context_results}

        for result in results:
            if result.chunk_id in context_map:
                ctx = context_map[result.chunk_id]
                result.context_before = ctx.get("context_before")
                result.context_after = ctx.get("context_after")

        return results

    def get_document_info(self, doc_number: str) -> Optional[Dict]:
        query = """
        MATCH (d:Document {doc_number: $doc_number})
        RETURN d {.*} AS document
        """
        results = self._run_query(query, {"doc_number": doc_number})
        return results[0]["document"] if results else None

    def find_related_documents(self, doc_number: str) -> List[Dict]:
        query = """
        MATCH (d:Document {doc_number: $doc_number})
        OPTIONAL MATCH (d2:Document {doc_number: d.amends})
        OPTIONAL MATCH (d3:Document)
        WHERE $doc_number IN d3.amended_by
        RETURN
            collect(DISTINCT d2 {.*, relation: 'amends'}) +
            collect(DISTINCT d3 {.*, relation: 'amended_by'}) AS related
        """
        results = self._run_query(query, {"doc_number": doc_number})
        if results and results[0]["related"]:
            return [r for r in results[0]["related"] if r]
        return []



