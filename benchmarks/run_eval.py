import argparse
import sys
from datetime import datetime
from pathlib import Path

# Support running as a script from inside benchmarks/ (e.g. `python run_eval.py`).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.evaluator import PipelineEvaluator
from benchmarks.results import print_summary, save_results


def _parse_k_values(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _parse_csv(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    values = [x.strip() for x in raw.split(",") if x.strip()]
    return values or None


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate legal/verdict retrieval using ViLeXa-style qrels format")
    parser.add_argument("--mode", choices=["legal", "verdict"], required=True)
    parser.add_argument("--data-dir", required=True, help="Path containing queries.jsonl and qrels/<split>.jsonl")
    parser.add_argument("--split", default="test")
    parser.add_argument("--collection", default="bench_zalo_legal", help="Qdrant collection override (useful for benchmark-specific index)")
    parser.add_argument("--k-values", default="1,3,5,10,20")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--per-query", action="store_true")
    parser.add_argument("--output", default=None)

    # Legal filters
    parser.add_argument("--query-date", default=None)
    parser.add_argument("--doc-types", default=None, help="Comma-separated document types")

    # Verdict filters
    parser.add_argument("--ip-types", default=None, help="Comma-separated IP types")
    parser.add_argument("--trial-level", default=None)

    args = parser.parse_args()

    evaluator = PipelineEvaluator.create(data_dir=args.data_dir, mode=args.mode, split=args.split)
    result = evaluator.evaluate(
        k_values=_parse_k_values(args.k_values),
        limit=args.limit,
        save_per_query=args.per_query,
        query_date=args.query_date,
        doc_types=_parse_csv(args.doc_types),
        ip_types=_parse_csv(args.ip_types),
        trial_level=args.trial_level,
        collection_name=args.collection,
    )

    print_summary(result)

    # Helpful diagnosis for common dataset/index mismatch case.
    precision = result.aggregate_metrics.get("precision", {})
    recall = result.aggregate_metrics.get("recall", {})
    all_zero_precision = all(float(v) == 0.0 for v in precision.values()) if precision else False
    all_zero_recall = all(float(v) == 0.0 for v in recall.values()) if recall else False
    if all_zero_precision and all_zero_recall and float(result.aggregate_metrics.get("mrr", 0.0)) == 0.0:
        print("\n[WARNING] All metrics are zero.")
        print("Likely cause: qrels corpus IDs do not align with your currently indexed collection.")
        print("For Zalo dataset, ensure your retriever index contains the same document/article IDs used in qrels.")
        print("Otherwise, create an internal benchmark dataset (queries + qrels) from your own corpus.")

    if args.output:
        out_path = args.output
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = str(Path(__file__).resolve().parent / "results" / f"{args.mode}_{stamp}.json")
    saved = save_results(result, out_path)
    print(f"Saved: {saved}")


if __name__ == "__main__":
    main()
