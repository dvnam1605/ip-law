import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from benchmarks.dataset import EvalDataset
from benchmarks.metrics import aggregate_metrics, compute_metrics
from benchmarks.pipeline_adapter import get_retriever_adapter
from benchmarks.results import EvalResult


@dataclass
class PipelineEvaluator:
    dataset: EvalDataset
    mode: str

    @classmethod
    def create(cls, data_dir: str, mode: str, split: str = "test") -> "PipelineEvaluator":
        dataset = EvalDataset.load(data_dir=data_dir, split=split)
        return cls(dataset=dataset, mode=mode)

    def evaluate(
        self,
        k_values: List[int],
        limit: Optional[int] = None,
        save_per_query: bool = False,
        **adapter_kwargs,
    ) -> EvalResult:
        adapter = get_retriever_adapter(self.mode, **adapter_kwargs)
        max_k = max(k_values)
        queries = self.dataset.get_eval_queries()
        if limit is not None:
            queries = queries[:limit]

        all_metrics = []
        per_query = [] if save_per_query else None

        start = time.perf_counter()
        for query_id, query_text in queries:
            retrieved = adapter.retrieve(query_text, k=max_k)
            relevant = self.dataset.get_relevant_docs(query_id)
            m = compute_metrics(retrieved, relevant, k_values)
            all_metrics.append(m)

            if save_per_query:
                per_query.append(
                    {
                        "query_id": query_id,
                        "query_text": query_text,
                        "retrieved": retrieved,
                        "relevant": list(relevant),
                        "metrics": m,
                    }
                )

        runtime = time.perf_counter() - start
        aggregate = aggregate_metrics(all_metrics, k_values)

        return EvalResult(
            config={
                "mode": self.mode,
                "adapter": adapter.name,
                "k_values": k_values,
                "num_queries": len(queries),
            },
            aggregate_metrics=aggregate,
            per_query_results=per_query,
            runtime_seconds=runtime,
        )
