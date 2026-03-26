import os
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from backend.core.config import config

from neo4j import AsyncGraphDatabase

from backend.runtime.retrievers.qdrant import QdrantSearchClient, VERDICT_COLLECTION

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
    """Async dense retriever: Qdrant vector search + Neo4j context expansion."""

    def __init__(self, uri=None, user=None, password=None,
                 embedding_model_path=None, qdrant_url=None):
        self.uri = uri or os.getenv("NEO4J_URI") or config.NEO4J_URI
        self.user = user or os.getenv("NEO4J_USER") or config.NEO4J_USER
        self.password = password or os.getenv("NEO4J_PASSWORD") or config.NEO4J_PASSWORD
        self.driver = AsyncGraphDatabase.driver(self.uri, auth=(self.user, self.password))

        # Qdrant client for vector search
        self.qdrant = QdrantSearchClient(
            url=qdrant_url,
            embedding_model_path=embedding_model_path
        )
        self.embedding_model = self.qdrant.embedding_model
        self.collection_name = os.getenv("QDRANT_VERDICT_COLLECTION", VERDICT_COLLECTION)

        # Project-wide setting: dense-only retrieval.
        self.use_neo4j_prefilter = (os.getenv("VERDICT_PREFILTER_NEO4J", "0").strip().lower() in {"1", "true", "yes", "on"})

    async def close(self):
        await self.driver.close()
        await self.qdrant.close()

    async def _run_query(self, query: str, params: Dict = None) -> List[Dict]:
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return await result.data()

    async def search(
        self,
        query: str,
        ip_types: List[str] = None,
        trial_level: str = None,
        top_k: int = 10,
        expand_context: bool = True,
        context_window: int = 1,
        boost_reasoning: bool = True,
    ) -> List[RetrievedVerdictChunk]:
        candidates = None
        if self.use_neo4j_prefilter:
            candidates = await self._filter_candidates(ip_types, trial_level)
            if not candidates:
                return []

        fetch_k = top_k * 2 if boost_reasoning else top_k

        ranked = await self._vector_search_ranked(query, candidates, fetch_k)

        results = await self._hydrate_chunks(ranked, top_k=fetch_k)

        if boost_reasoning and results:
            for r in results:
                r.score *= SECTION_BOOSTS.get(r.section_type, 1.0)
            results.sort(key=lambda x: x.score, reverse=True)
            results = results[:top_k]

        results = await self._ensure_key_sections(results)

        if expand_context and results:
            await self._expand_context(results, context_window)

        return results

    async def _ensure_key_sections(self, results: List[RetrievedVerdictChunk]) -> List[RetrievedVerdictChunk]:
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
            for r in await self._run_query(cypher)
            if r["vchunk_id"] not in existing_ids
        ]
        return results + extra

    async def _filter_candidates(self, ip_types=None, trial_level=None) -> List[str]:
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
        return [r["vchunk_id"] for r in await self._run_query(query, params)]

    async def _vector_search_ranked(
        self,
        query: str,
        candidate_ids: List[str],
        top_k: int,
    ) -> List[Tuple[str, float]]:
        """Dense vector retrieval from Qdrant."""
        if not self.embedding_model:
            return []

        query_embedding = await self.qdrant.encode(query)

        try:
            return await self.qdrant.search(
                collection=self.collection_name,
                query_embedding=query_embedding,
                id_field="vchunk_id",
                candidate_ids=candidate_ids,
                top_k=top_k,
            )
        except Exception as e:
            print(f"⚠️ Qdrant search failed: {e}")
            return []

    async def _hydrate_chunks(
        self,
        ranked_vchunk_ids: List[Tuple[str, float]],
        top_k: int,
    ) -> List[RetrievedVerdictChunk]:
        """Hydrate ranked verdict chunk IDs to full records via Neo4j."""
        if not ranked_vchunk_ids:
            return []

        vchunk_ids = [vid for vid, _ in ranked_vchunk_ids[:top_k]]
        score_map = {vid: score for vid, score in ranked_vchunk_ids}

        cypher = f"""
        UNWIND $vchunk_ids AS vid
        MATCH (vc:VerdictChunk {{vchunk_id: vid}})-[:PART_OF_VERDICT]->(v:Verdict)
        WITH vc, v, 0.0 AS score
        {_RETURN_CLAUSE}
        """

        rows = await self._run_query(cypher, {"vchunk_ids": vchunk_ids})
        row_map = {r["vchunk_id"]: r for r in rows if r.get("vchunk_id")}
        chunks: List[RetrievedVerdictChunk] = []
        for vid in vchunk_ids:
            r = row_map.get(vid)
            if not r:
                continue
            chunk = RetrievedVerdictChunk.from_record(r)
            chunk.score = score_map.get(vid, 0.0)
            chunks.append(chunk)

        return chunks

    async def _expand_context(self, results: List[RetrievedVerdictChunk], window: int = 1):
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
        ctx_data = await self._run_query(cypher, {"chunk_ids": chunk_ids})
        ctx_map = {r["vchunk_id"]: r for r in ctx_data}
        for result in results:
            ctx = ctx_map.get(result.vchunk_id, {})
            result.context_before = ctx.get("context_before")
            result.context_after = ctx.get("context_after")

    async def get_full_verdict(self, case_number: str) -> List[RetrievedVerdictChunk]:
        cypher = f"""
        MATCH (vc:VerdictChunk)-[:PART_OF_VERDICT]->(v:Verdict {{case_number: $case_number}})
        WITH vc, v, 1.0 AS score
        ORDER BY vc.chunk_index
        {_RETURN_CLAUSE}
        """
        return [
            RetrievedVerdictChunk.from_record(r)
            for r in await self._run_query(cypher, {"case_number": case_number})
        ]
