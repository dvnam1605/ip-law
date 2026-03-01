import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date
from dataclasses import dataclass
import numpy as np

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


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
    Query Flow:
    1. Cypher filter: văn bản đang có hiệu lực
    2. Vector search trên tập đã lọc
    3. Dùng NEXT để lấy đủ context
    """
    
    def __init__(
        self,
        uri: str = None,
        user: str = None,
        password: str = None,
        embedding_model_path: str = None,
    ):
        if not NEO4J_AVAILABLE:
            raise ImportError("neo4j package required: pip install neo4j")
        
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "aa")
        
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        
        # Load embedding model
        self.embedding_model = None
        if embedding_model_path and SENTENCE_TRANSFORMERS_AVAILABLE:
            print(f"Loading embedding model from {embedding_model_path}...")
            self.embedding_model = SentenceTransformer(embedding_model_path)
            print(f"Model loaded. Dimension: {self.embedding_model.get_sentence_embedding_dimension()}")
    
    def close(self):
        self.driver.close()
    
    def _run_query(self, query: str, params: Dict = None) -> List[Dict]:
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]
    
    def encode_query(self, query: str) -> List[float]:
        if self.embedding_model is None:
            raise ValueError("Embedding model not loaded")
        embedding = self.embedding_model.encode(query)
        return embedding.tolist()
    
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
        """
        Args:
            query: Câu hỏi tìm kiếm
            query_date: Ngày truy vấn (YYYY-MM-DD), default = today
            doc_types: Filter theo loại văn bản ['Luật', 'Nghị định', ...]
            status: Status của văn bản ('active', 'expired', 'replaced')
            top_k: Số kết quả trả về
            expand_context: Có lấy thêm context từ NEXT không
            context_window: Số chunks trước/sau để lấy context
        """
        
        if query_date is None:
            query_date = datetime.now().strftime("%Y-%m-%d")
        
        candidates = self._filter_by_validity(query_date, doc_types, status)
        
        if not candidates:
            print("⚠️ No valid documents found for the given criteria")
            return []
        
        print(f"📋 Found {len(candidates)} candidate chunks after filtering")
        if len(candidates) <= 10:
            print(f"   Candidate IDs: {candidates}")
        else:
            print(f"   Sample IDs: {candidates[:5]}...")
        
        if self.embedding_model:
            results = self._vector_search(query, candidates, top_k)
        else:
            results = self._keyword_search(query, candidates, top_k)
        
        if expand_context and results:
            results = self._expand_context(results, context_window)
        
        return results
    
    def _filter_by_validity(
        self,
        query_date: str,
        doc_types: List[str] = None,
        status: str = "active",
    ) -> List[str]:
        
        conditions = ["d.status = $status"]
        params = {"status": status, "query_date": query_date}
        
        # effective_date is stored as string "YYYY-MM-DD", use string comparison
        conditions.append("(d.effective_date IS NULL OR d.effective_date <= $query_date)")
        
        # Doc type filter
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
    
    def _vector_search(
        self,
        query: str,
        candidate_ids: List[str],
        top_k: int,
    ) -> List[RetrievedChunk]:
        query_embedding = self.encode_query(query)
        
        
        cypher_query = """
        UNWIND $candidate_ids AS cid
        MATCH (c:Chunk {chunk_id: cid})-[:PART_OF]->(d:Document)
        WHERE c.embedding IS NOT NULL
        
        WITH c, d,
             reduce(dot = 0.0, i IN range(0, size(c.embedding)-1) | 
                    dot + c.embedding[i] * $query_embedding[i]) AS dot_product,
             reduce(norm_c = 0.0, i IN range(0, size(c.embedding)-1) | 
                    norm_c + c.embedding[i] * c.embedding[i]) AS norm_c,
             reduce(norm_q = 0.0, i IN range(0, size($query_embedding)-1) | 
                    norm_q + $query_embedding[i] * $query_embedding[i]) AS norm_q
        
        WITH c, d, dot_product / (sqrt(norm_c) * sqrt(norm_q)) AS score
        ORDER BY score DESC
        LIMIT $top_k
        
        RETURN 
            c.chunk_id AS chunk_id,
            c.content AS content,
            score,
            c.dieu AS dieu,
            c.dieu_title AS dieu_title,
            c.chuong AS chuong,
            d.doc_name AS doc_name,
            d.doc_number AS doc_number,
            d.doc_type AS doc_type,
            d.effective_date AS effective_date
        """
        
        try:
            results = self._run_query(cypher_query, {
                "candidate_ids": candidate_ids,
                "query_embedding": query_embedding,
                "top_k": top_k
            })
        except Exception as e:
            print(f"⚠️ Vector search failed: {e}")
            print("   Falling back to keyword search")
            return self._keyword_search(query, candidate_ids, top_k)
        
        return [
            RetrievedChunk(
                chunk_id=r["chunk_id"],
                content=r["content"],
                score=r["score"],
                dieu=r["dieu"],
                dieu_title=r["dieu_title"],
                chuong=r["chuong"],
                doc_name=r["doc_name"],
                doc_number=r["doc_number"],
                doc_type=r["doc_type"],
                effective_date=str(r["effective_date"]) if r["effective_date"] else None,
            )
            for r in results
        ]
    
    def _keyword_search(
        self,
        query: str,
        candidate_ids: List[str],
        top_k: int,
    ) -> List[RetrievedChunk]:
        keywords = [w.lower() for w in query.split() if len(w) > 2]
        
        if not keywords:
            return []
        
        contains_conditions = " OR ".join([f"toLower(c.content) CONTAINS '{kw}'" for kw in keywords[:5]])
        
        cypher_query = f"""
        UNWIND $candidate_ids AS cid
        MATCH (c:Chunk {{chunk_id: cid}})-[:PART_OF]->(d:Document)
        WHERE {contains_conditions}
        
        WITH c, d, 
             size([kw IN $keywords WHERE toLower(c.content) CONTAINS kw]) AS match_count
        ORDER BY match_count DESC
        LIMIT $top_k
        
        RETURN 
            c.chunk_id AS chunk_id,
            c.content AS content,
            toFloat(match_count) / size($keywords) AS score,
            c.dieu AS dieu,
            c.dieu_title AS dieu_title,
            c.chuong AS chuong,
            d.doc_name AS doc_name,
            d.doc_number AS doc_number,
            d.doc_type AS doc_type,
            d.effective_date AS effective_date
        """
        
        results = self._run_query(cypher_query, {
            "candidate_ids": candidate_ids,
            "keywords": keywords,
            "top_k": top_k
        })
        
        return [
            RetrievedChunk(
                chunk_id=r["chunk_id"],
                content=r["content"],
                score=r["score"],
                dieu=r["dieu"],
                dieu_title=r["dieu_title"],
                chuong=r["chuong"],
                doc_name=r["doc_name"],
                doc_number=r["doc_number"],
                doc_type=r["doc_type"],
                effective_date=str(r["effective_date"]) if r["effective_date"] else None,
            )
            for r in results
        ]
    
    def _expand_context(
        self,
        results: List[RetrievedChunk],
        context_window: int = 1,
    ) -> List[RetrievedChunk]:
        """
        Mở rộng context qua NEXT relationships.
        Note: Cypher doesn't allow parameters in variable-length relationships.
        """
        
        chunk_ids = [r.chunk_id for r in results]
        
        # Note: Cypher doesn't allow parameters in variable-length relationships
        # So we need to build the query with the window value directly
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
        
        context_results = self._run_query(cypher_query, {
            "chunk_ids": chunk_ids
        })
        
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
        
        // Documents that this one amends
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


def main():
    print("="*60)
    print("🔍 NEO4J LEGAL RAG RETRIEVER TEST")
    print("="*60)
    
    # Initialize retriever
    embedding_path = "./vietnamese_embedding"
    if not os.path.exists(embedding_path):
        embedding_path = None
        print("⚠️ Embedding model not found, using keyword search")
    
    try:
        retriever = Neo4jLegalRetriever(
            embedding_model_path=embedding_path
        )
    except Exception as e:
        print(f"❌ Failed to initialize retriever: {e}")
        return
    
    # Test queries
    test_queries = [
        "Điều kiện bảo hộ quyền tác giả",
        "Xử phạt vi phạm hành chính về sở hữu trí tuệ",
        "Đăng ký nhãn hiệu như thế nào",
    ]
    
    for query in test_queries:
        print(f"\n{'─'*40}")
        print(f"🔎 Query: {query}")
        print(f"{'─'*40}")
        
        results = retriever.search(
            query=query,
            query_date="2024-01-01",
            doc_types=["Luật", "Nghị định"],
            top_k=3,
            expand_context=True,
        )
        
        for i, r in enumerate(results, 1):
            print(f"\n📄 Result {i} (score: {r.score:.4f})")
            print(f"   Document: {r.doc_name}")
            print(f"   Điều: {r.dieu} - {r.dieu_title}")
            print(f"   Content: {r.content[:200]}...")
            if r.context_before:
                print(f"   [Has context before]")
            if r.context_after:
                print(f"   [Has context after]")
    
    retriever.close()
    print("\n✅ Test complete!")


if __name__ == "__main__":
    main()
