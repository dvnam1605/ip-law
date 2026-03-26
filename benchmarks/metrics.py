from typing import Dict, List, Set


def deduplicate_retrieved(retrieved: List[str]) -> List[str]:
    seen = set()
    out = []
    for doc_id in retrieved:
        if doc_id not in seen:
            seen.add(doc_id)
            out.append(doc_id)
    return out


def precision_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / k


def recall_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def reciprocal_rank(retrieved: List[str], relevant: Set[str]) -> float:
    for idx, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant:
            return 1.0 / idx
    return 0.0


def compute_metrics(retrieved: List[str], relevant: Set[str], k_values: List[int]) -> Dict:
    docs = deduplicate_retrieved(retrieved)
    precision = {k: precision_at_k(docs, relevant, k) for k in k_values}
    recall = {k: recall_at_k(docs, relevant, k) for k in k_values}
    mrr = reciprocal_rank(docs, relevant)
    return {"precision": precision, "recall": recall, "mrr": mrr}


def aggregate_metrics(all_metrics: List[Dict], k_values: List[int]) -> Dict:
    n = len(all_metrics)
    if n == 0:
        return {"precision": {k: 0.0 for k in k_values}, "recall": {k: 0.0 for k in k_values}, "mrr": 0.0}

    precision = {k: sum(m["precision"][k] for m in all_metrics) / n for k in k_values}
    recall = {k: sum(m["recall"][k] for m in all_metrics) / n for k in k_values}
    mrr = sum(m["mrr"] for m in all_metrics) / n
    return {"precision": precision, "recall": recall, "mrr": mrr}
