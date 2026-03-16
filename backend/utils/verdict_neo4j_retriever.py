import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from neo4j import GraphDatabase

from backend.utils.qdrant_retriever import QdrantSearchClient, VERDICT_COLLECTION

SECTION_BOOSTS = {
    'reasoning': 1.3,
    'decision_item': 1.1,
}

_RETURN_CLAUSE = """
    RETURN
        vc.vchunk_id AS vchunk_id, vc.content AS content, score,
        vc.section_type AS section_type, vc.point_number AS point_number,
        vc.party_role AS party_role, vc.item_number AS item_number,
        v.case_number AS case_number, v.court_name AS court_name,
        v.judgment_date AS judgment_date, v.dispute_type AS dispute_type,
        v.ip_types AS ip_types, v.plaintiff AS plaintiff,
        v.defendant AS defendant, v.trial_level AS trial_level,
        v.summary AS summary
"""


@dataclass
class RetrievedVerdictChunk:
    vchunk_id: str
    content: str
    score: float
    section_type: str
    point_number: str
    party_role: str
    item_number: str
    case_number: str
    court_name: str
    judgment_date: str
    dispute_type: str
    ip_types: Any
    plaintiff: str
    defendant: str
    trial_level: str
    summary: str
    context_before: Optional[str] = None
    context_after: Optional[str] = None

    @classmethod
    def from_record(cls, r: Dict) -> 'RetrievedVerdictChunk':
        return cls(
            vchunk_id=r["vchunk_id"],
            content=r["content"],
            score=r["score"],
            section_type=r.get("section_type") or "",
            point_number=r.get("point_number") or "",
            party_role=r.get("party_role") or "",
            item_number=r.get("item_number") or "",
            case_number=r.get("case_number") or "",
            court_name=r.get("court_name") or "",
            judgment_date=r.get("judgment_date") or "",
            dispute_type=r.get("dispute_type") or "",
            ip_types=r.get("ip_types") or [],
            plaintiff=r.get("plaintiff") or "",
            defendant=r.get("defendant") or "",
            trial_level=r.get("trial_level") or "",
            summary=r.get("summary") or "",
        )


class Neo4jVerdictRetriever:
    """Hybrid retriever: Qdrant vector search + Neo4j context expansion."""

    def __init__(self, uri=None, user=None, password=None,
                 embedding_model_path=None, qdrant_url=None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "dvnam1605")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

        # Qdrant client for vector search
        self.qdrant = QdrantSearchClient(
            url=qdrant_url,
            embedding_model_path=embedding_model_path
        )
        self.embedding_model = self.qdrant.embedding_model

    def close(self):
        self.driver.close()
        self.qdrant.close()

    def _run_query(self, query: str, params: Dict = None) -> List[Dict]:
        with self.driver.session() as session:
            return [r.data() for r in session.run(query, params or {})]

    def search(
        self,
        query: str,
        ip_types: List[str] = None,
        trial_level: str = None,
        top_k: int = 10,
        expand_context: bool = True,
        context_window: int = 1,
        boost_reasoning: bool = True,
    ) -> List[RetrievedVerdictChunk]:
        candidates = self._filter_candidates(ip_types, trial_level)
        if not candidates:
            return []

        fetch_k = top_k * 2 if boost_reasoning else top_k
        if self.embedding_model:
            results = self._vector_search(query, candidates, fetch_k)
        else:
            results = self._keyword_search(query, candidates, fetch_k)

        if boost_reasoning and results:
            for r in results:
                r.score *= SECTION_BOOSTS.get(r.section_type, 1.0)
            results.sort(key=lambda x: x.score, reverse=True)
            results = results[:top_k]

        results = self._ensure_key_sections(results)

        if expand_context and results:
            self._expand_context(results, context_window)

        return results

    def _ensure_key_sections(self, results: List[RetrievedVerdictChunk]) -> List[RetrievedVerdictChunk]:
        if not results:
            return results

        existing_ids = {r.vchunk_id for r in results}
        case_numbers = {r.case_number for r in results if r.case_number}
        case_sections = {}
        for r in results:
            if r.case_number:
                case_sections.setdefault(r.case_number, set()).add(r.section_type)

        KEY_SECTIONS = ['reasoning', 'decision_item']
        missing_cases = []
        for cn in case_numbers:
            existing = case_sections.get(cn, set())
            missing = [s for s in KEY_SECTIONS if s not in existing]
            if missing:
                missing_cases.append((cn, missing))

        if not missing_cases:
            return results

        conditions = []
        for cn, sections in missing_cases:
            sec_list = "[" + ",".join(f"'{s}'" for s in sections) + "]"
            conditions.append(f"(v.case_number = '{cn}' AND vc.section_type IN {sec_list})")

        where = " OR ".join(conditions)
        cypher = f"""
        MATCH (vc:VerdictChunk)-[:PART_OF_VERDICT]->(v:Verdict)
        WHERE {where}
        WITH vc, v, 0.5 AS score
        ORDER BY v.case_number, vc.chunk_index
        {_RETURN_CLAUSE}
        """
        extra = [
            RetrievedVerdictChunk.from_record(r)
            for r in self._run_query(cypher)
            if r["vchunk_id"] not in existing_ids
        ]
        return results + extra

    def _filter_candidates(self, ip_types=None, trial_level=None) -> List[str]:
        conditions, params = [], {}
        if ip_types:
            conditions.append("ANY(ip IN v.ip_types WHERE ip IN $ip_types)")
            params["ip_types"] = ip_types
        if trial_level:
            conditions.append("v.trial_level = $trial_level")
            params["trial_level"] = trial_level

        where = " AND ".join(conditions) if conditions else "TRUE"
        query = f"""
        MATCH (vc:VerdictChunk)-[:PART_OF_VERDICT]->(v:Verdict)
        WHERE {where}
        RETURN vc.vchunk_id AS vchunk_id
        """
        return [r["vchunk_id"] for r in self._run_query(query, params)]

    def _vector_search(self, query: str, candidate_ids: List[str],
                       top_k: int) -> List[RetrievedVerdictChunk]:
        """Vector search via Qdrant, then fetch metadata from Neo4j."""
        query_embedding = self.qdrant.encode(query)

        try:
            qdrant_results = self.qdrant.search(
                collection=VERDICT_COLLECTION,
                query_embedding=query_embedding,
                id_field="vchunk_id",
                candidate_ids=candidate_ids,
                top_k=top_k,
            )
        except Exception as e:
            print(f"⚠️ Qdrant search failed: {e}, falling back to keyword search")
            return self._keyword_search(query, candidate_ids, top_k)

        if not qdrant_results:
            return self._keyword_search(query, candidate_ids, top_k)

        # Map vchunk_ids back to Neo4j for full metadata
        vchunk_ids = [vid for vid, _ in qdrant_results]
        score_map = {vid: score for vid, score in qdrant_results}

        cypher = f"""
        UNWIND $vchunk_ids AS vid
        MATCH (vc:VerdictChunk {{vchunk_id: vid}})-[:PART_OF_VERDICT]->(v:Verdict)
        WITH vc, v, 0.0 AS score
        {_RETURN_CLAUSE}
        """

        results = self._run_query(cypher, {"vchunk_ids": vchunk_ids})
        chunks = []
        for r in results:
            chunk = RetrievedVerdictChunk.from_record(r)
            chunk.score = score_map.get(r["vchunk_id"], 0)
            chunks.append(chunk)

        return chunks

    def _keyword_search(self, query: str, candidate_ids: List[str],
                        top_k: int) -> List[RetrievedVerdictChunk]:
        keywords = [w.lower() for w in query.split() if len(w) > 2]
        if not keywords:
            return []

        contains = " OR ".join(f"toLower(vc.content) CONTAINS '{kw}'" for kw in keywords[:5])
        cypher = f"""
        UNWIND $candidate_ids AS cid
        MATCH (vc:VerdictChunk {{vchunk_id: cid}})-[:PART_OF_VERDICT]->(v:Verdict)
        WHERE {contains}
        WITH vc, v,
             size([kw IN $keywords WHERE toLower(vc.content) CONTAINS kw]) AS match_count
        WITH vc, v, toFloat(match_count) / size($keywords) AS score
        ORDER BY score DESC
        LIMIT $top_k
        {_RETURN_CLAUSE}
        """
        results = self._run_query(cypher, {
            "candidate_ids": candidate_ids, "keywords": keywords, "top_k": top_k,
        })
        return [RetrievedVerdictChunk.from_record(r) for r in results]

    def _expand_context(self, results: List[RetrievedVerdictChunk], window: int = 1):
        chunk_ids = [r.vchunk_id for r in results]
        cypher = f"""
        UNWIND $chunk_ids AS cid
        MATCH (vc:VerdictChunk {{vchunk_id: cid}})
        OPTIONAL MATCH (prev)-[:NEXT_IN_VERDICT*1..{window}]->(vc)
        WITH vc, collect(prev.content) AS prev_contents
        OPTIONAL MATCH (vc)-[:NEXT_IN_VERDICT*1..{window}]->(next)
        WITH vc, prev_contents, collect(next.content) AS next_contents
        RETURN
            vc.vchunk_id AS vchunk_id,
            CASE WHEN size(prev_contents) > 0
                 THEN reduce(s = '', x IN prev_contents | s + x + '\\n---\\n')
                 ELSE null END AS context_before,
            CASE WHEN size(next_contents) > 0
                 THEN reduce(s = '', x IN next_contents | s + x + '\\n---\\n')
                 ELSE null END AS context_after
        """
        ctx_map = {r["vchunk_id"]: r for r in self._run_query(cypher, {"chunk_ids": chunk_ids})}
        for result in results:
            ctx = ctx_map.get(result.vchunk_id, {})
            result.context_before = ctx.get("context_before")
            result.context_after = ctx.get("context_after")

    def get_full_verdict(self, case_number: str) -> List[RetrievedVerdictChunk]:
        cypher = f"""
        MATCH (vc:VerdictChunk)-[:PART_OF_VERDICT]->(v:Verdict {{case_number: $case_number}})
        WITH vc, v, 1.0 AS score
        ORDER BY vc.chunk_index
        {_RETURN_CLAUSE}
        """
        return [
            RetrievedVerdictChunk.from_record(r)
            for r in self._run_query(cypher, {"case_number": case_number})
        ]
