import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple


@dataclass
class EvalDataset:
    """Dataset in Zalo/ViLeXa qrels format."""

    queries: Dict[str, str] = field(default_factory=dict)
    qrels: Dict[str, Set[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, data_dir: str, split: str = "test") -> "EvalDataset":
        root = Path(data_dir)
        queries = {}
        qrels = {}

        with open(root / "queries.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    queries[row["_id"]] = row["text"]

        with open(root / "qrels" / f"{split}.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    qid = row["query-id"]
                    cid = row["corpus-id"]
                    qrels.setdefault(qid, set()).add(cid)

        return cls(queries=queries, qrels=qrels)

    def get_eval_queries(self) -> List[Tuple[str, str]]:
        out = []
        for qid in self.qrels:
            text = self.queries.get(qid)
            if text:
                out.append((qid, text))
        return out

    def get_relevant_docs(self, query_id: str) -> Set[str]:
        return self.qrels.get(query_id, set())
