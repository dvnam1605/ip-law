import re
import os
from abc import ABC, abstractmethod
from typing import List, Optional


class BaseRetrieverAdapter(ABC):
    @abstractmethod
    def retrieve(self, query: str, k: int = 20) -> List[str]:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


class LegalPipelineAdapter(BaseRetrieverAdapter):
    """Adapter for backend legal retriever via GeminiRAGPipeline.retriever."""

    def __init__(
        self,
        query_date: Optional[str] = None,
        doc_types: Optional[List[str]] = None,
        collection_name: Optional[str] = None,
    ):
        if collection_name:
            os.environ["QDRANT_LEGAL_COLLECTION"] = collection_name
        from backend.core.pipeline.rag_pipeline import get_pipeline

        self.pipeline = get_pipeline()
        self.query_date = query_date
        self.doc_types = doc_types
        self.collection_name = collection_name

    @staticmethod
    def _to_qrels_corpus_id(result) -> Optional[str]:
        """Map retriever record to Zalo/ViLeXa qrels corpus-id format: doc_number+dieu."""
        doc_number = (getattr(result, "doc_number", None) or "").strip().lower().replace(" ", "")
        dieu_text = (getattr(result, "dieu", None) or "").strip().lower()
        if not doc_number or not dieu_text:
            return None

        match = re.search(r"(\d+[a-z]?)", dieu_text)
        if not match:
            return None

        dieu_id = match.group(1)
        return f"{doc_number}+{dieu_id}"

    def retrieve(self, query: str, k: int = 20) -> List[str]:
        retriever = self.pipeline.retriever

        # Benchmark retrieval quality directly from retriever ranking IDs,
        # skipping Neo4j hydration/context expansion when supported.
        if hasattr(retriever, "search_ids"):
            return retriever.search_ids(
                query=query,
                top_k=k,
                query_date=self.query_date,
                doc_types=self.doc_types,
            )

        results = retriever.search(
            query=query,
            top_k=k,
            query_date=self.query_date,
            doc_types=self.doc_types,
            expand_context=False,
            context_window=0,
        )
        out: List[str] = []
        seen = set()
        for r in results:
            corpus_id = self._to_qrels_corpus_id(r)
            if corpus_id and corpus_id not in seen:
                seen.add(corpus_id)
                out.append(corpus_id)

        # Fallback for non-Zalo datasets that store chunk IDs directly.
        if not out:
            for r in results:
                chunk_id = getattr(r, "chunk_id", None)
                if chunk_id and chunk_id not in seen:
                    seen.add(chunk_id)
                    out.append(chunk_id)

        return out

    @property
    def name(self) -> str:
        return "legal-retriever"


class VerdictPipelineAdapter(BaseRetrieverAdapter):
    """Adapter for backend verdict retriever via VerdictRAGPipeline.retriever."""

    def __init__(self, ip_types: Optional[List[str]] = None, trial_level: Optional[str] = None):
        from backend.core.pipeline.verdict_rag_pipeline import get_verdict_pipeline

        self.pipeline = get_verdict_pipeline()
        self.ip_types = ip_types
        self.trial_level = trial_level

    def retrieve(self, query: str, k: int = 20) -> List[str]:
        results = self.pipeline.retriever.search(
            query=query,
            top_k=k,
            ip_types=self.ip_types,
            trial_level=self.trial_level,
            expand_context=False,
            context_window=0,
            boost_reasoning=False,
        )
        return [r.vchunk_id for r in results if getattr(r, "vchunk_id", None)]

    @property
    def name(self) -> str:
        return "verdict-retriever"


def get_retriever_adapter(mode: str, **kwargs) -> BaseRetrieverAdapter:
    mode = mode.lower()
    if mode == "legal":
        return LegalPipelineAdapter(
            query_date=kwargs.get("query_date"),
            doc_types=kwargs.get("doc_types"),
            collection_name=kwargs.get("collection_name"),
        )
    if mode == "verdict":
        return VerdictPipelineAdapter(
            ip_types=kwargs.get("ip_types"),
            trial_level=kwargs.get("trial_level"),
        )
    raise ValueError(f"Unsupported mode: {mode}. Use 'legal' or 'verdict'.")
