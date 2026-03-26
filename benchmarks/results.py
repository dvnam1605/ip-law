import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class EvalResult:
    config: Dict[str, Any] = field(default_factory=dict)
    aggregate_metrics: Dict[str, Any] = field(default_factory=dict)
    per_query_results: Optional[List[Dict[str, Any]]] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    runtime_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "config": self.config,
            "aggregate_metrics": {
                k: ({str(kk): vv for kk, vv in v.items()} if isinstance(v, dict) else v)
                for k, v in self.aggregate_metrics.items()
            },
            "timestamp": self.timestamp,
            "runtime_seconds": self.runtime_seconds,
        }
        if self.per_query_results is not None:
            payload["per_query_results"] = self.per_query_results
        return payload


def save_results(result: EvalResult, output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    return str(path)


def print_summary(result: EvalResult) -> None:
    print("\n" + "=" * 60)
    print("PIPELINE RETRIEVAL EVALUATION")
    print("=" * 60)
    print("Mode:", result.config.get("mode"))
    print("Queries:", result.config.get("num_queries"))
    print("Runtime (s):", f"{(result.runtime_seconds or 0):.2f}")
    print("\nMetrics:")
    print("k\tP@k\tR@k")
    precision_raw = result.aggregate_metrics.get("precision", {})
    recall_raw = result.aggregate_metrics.get("recall", {})
    precision = {int(k): v for k, v in precision_raw.items()}
    recall = {int(k): v for k, v in recall_raw.items()}
    ks = sorted(precision.keys())
    for k in ks:
        p = precision.get(k, 0.0)
        r = recall.get(k, 0.0)
        print(f"{k}\t{p:.4f}\t{r:.4f}")
    print(f"MRR\t{result.aggregate_metrics.get('mrr', 0):.4f}")
