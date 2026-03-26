import argparse
import json
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from qdrant_client import QdrantClient

try:
    from neo4j import GraphDatabase

    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "internal_legal_benchmark"


@dataclass
class BenchmarkRow:
    query_id: str
    query_text: str
    corpus_id: str


def _normalize_doc_number(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "")
    return text


def _extract_dieu_id(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if not text:
        return None
    match = re.search(r"(\d+[a-z]?)", text)
    if not match:
        return None
    return match.group(1)


def _build_corpus_id(payload: Dict[str, Any]) -> Optional[str]:
    doc_number = _normalize_doc_number(payload.get("doc_number"))
    dieu_id = _extract_dieu_id(payload.get("dieu"))
    if not doc_number or not dieu_id:
        return None
    return f"{doc_number}+{dieu_id}"


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _content_snippet(content: str, max_chars: int = 180) -> str:
    content = _clean_text(content)
    if not content:
        return ""
    snippet = content[:max_chars]
    if len(content) > max_chars:
        snippet = snippet.rstrip() + "..."
    return snippet


def _build_query(
    payload: Dict[str, Any],
    rng: random.Random,
    style: str,
) -> Optional[str]:
    dieu = _clean_text(payload.get("dieu"))
    dieu_title = _clean_text(payload.get("dieu_title"))
    doc_name = _clean_text(payload.get("doc_name"))
    doc_number = _clean_text(payload.get("doc_number"))
    content = _clean_text(payload.get("content"))

    templates: List[str] = []

    if dieu_title:
        templates.extend(
            [
                f"{dieu_title} được quy định như thế nào?",
                f"Quy định về {dieu_title} là gì?",
            ]
        )

    if dieu and doc_name:
        templates.extend(
            [
                f"{dieu} trong {doc_name} quy định gì?",
                f"Nội dung của {dieu} thuộc {doc_name} là gì?",
            ]
        )

    if dieu and doc_number:
        templates.append(f"{dieu} của văn bản {doc_number} quy định gì?")

    if content:
        snippet = _content_snippet(content)
        templates.append(f"Quy định sau nói về nội dung gì: {snippet}")

    if not templates:
        return None

    if style == "title":
        filtered = [t for t in templates if "được quy định" in t or "Quy định về" in t]
        return filtered[0] if filtered else templates[0]

    if style == "article":
        filtered = [t for t in templates if "Điều" in t or "điều" in t]
        return filtered[0] if filtered else templates[0]

    return rng.choice(templates)


def _iter_collection_payloads(
    client: QdrantClient,
    collection: str,
    batch_size: int,
):
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            limit=batch_size,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        if not points:
            break
        for point in points:
            yield point.payload or {}
        if next_offset is None:
            break
        offset = next_offset


def _load_active_corpus_ids(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    query_date: str,
) -> Set[str]:
    if not NEO4J_AVAILABLE:
        raise RuntimeError("neo4j package is required for --active-only mode. Install with: pip install neo4j")

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    cypher = """
    MATCH (c:Chunk)-[:PART_OF]->(d:Document)
    WHERE d.status = 'active'
      AND (d.effective_date IS NULL OR d.effective_date <= $query_date)
    RETURN d.doc_number AS doc_number, c.dieu AS dieu
    """

    out: Set[str] = set()
    with driver.session() as session:
        for row in session.run(cypher, {"query_date": query_date}):
            doc_number = _normalize_doc_number(row.get("doc_number"))
            dieu_id = _extract_dieu_id(row.get("dieu"))
            if doc_number and dieu_id:
                out.add(f"{doc_number}+{dieu_id}")

    driver.close()
    return out


def build_dataset(
    client: QdrantClient,
    collection: str,
    max_queries: int,
    style: str,
    seed: int,
    batch_size: int,
    active_corpus_ids: Optional[Set[str]] = None,
) -> Tuple[List[BenchmarkRow], int, int, int]:
    rng = random.Random(seed)
    dedup: Dict[str, Dict[str, Any]] = {}
    total_points = 0
    skipped_invalid = 0
    skipped_inactive = 0

    for payload in _iter_collection_payloads(client, collection, batch_size):
        total_points += 1
        corpus_id = _build_corpus_id(payload)
        if not corpus_id:
            skipped_invalid += 1
            continue
        if active_corpus_ids is not None and corpus_id not in active_corpus_ids:
            skipped_inactive += 1
            continue
        if corpus_id in dedup:
            continue
        dedup[corpus_id] = payload

    items = list(dedup.items())
    rng.shuffle(items)
    if max_queries > 0:
        items = items[:max_queries]

    rows: List[BenchmarkRow] = []
    for idx, (corpus_id, payload) in enumerate(items, start=1):
        q_text = _build_query(payload, rng=rng, style=style)
        if not q_text:
            continue
        query_id = f"int_{idx:06d}"
        rows.append(BenchmarkRow(query_id=query_id, query_text=q_text, corpus_id=corpus_id))

    return rows, total_points, skipped_invalid, skipped_inactive


def write_dataset(rows: List[BenchmarkRow], output_dir: Path, split: str) -> None:
    qrels_dir = output_dir / "qrels"
    qrels_dir.mkdir(parents=True, exist_ok=True)

    queries_path = output_dir / "queries.jsonl"
    qrels_path = qrels_dir / f"{split}.jsonl"

    with queries_path.open("w", encoding="utf-8") as fq:
        for row in rows:
            fq.write(json.dumps({"_id": row.query_id, "text": row.query_text}, ensure_ascii=False) + "\n")

    with qrels_path.open("w", encoding="utf-8") as fr:
        for row in rows:
            fr.write(
                json.dumps(
                    {
                        "query-id": row.query_id,
                        "corpus-id": row.corpus_id,
                        "score": 1,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build internal legal benchmark dataset from an existing Qdrant collection",
    )
    parser.add_argument("--collection", default="legal_chunks", help="Source Qdrant collection")
    parser.add_argument("--qdrant-url", default="http://192.168.1.199:6333")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--split", default="test")
    parser.add_argument("--max-queries", type=int, default=1000, help="Maximum unique corpus-id queries to generate")
    parser.add_argument("--style", choices=["mixed", "title", "article"], default="mixed")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--active-only", action="store_true", help="Keep only corpus IDs currently retrievable under active/effective-date filter")
    parser.add_argument("--query-date", default=datetime.now().strftime("%Y-%m-%d"), help="Date used by active filter, format YYYY-MM-DD")
    parser.add_argument("--neo4j-uri", default="bolt://127.0.0.1:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()

    client = QdrantClient(url=args.qdrant_url)
    collections = {c.name for c in client.get_collections().collections}
    if args.collection not in collections:
        raise RuntimeError(
            f"Collection '{args.collection}' not found in Qdrant at {args.qdrant_url}. "
            f"Available: {sorted(collections)}"
        )

    active_corpus_ids: Optional[Set[str]] = None
    if args.active_only:
        active_corpus_ids = _load_active_corpus_ids(
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
            query_date=args.query_date,
        )
        print(f"Active corpus IDs loaded from Neo4j: {len(active_corpus_ids)}")

    rows, total_points, skipped_invalid, skipped_inactive = build_dataset(
        client=client,
        collection=args.collection,
        max_queries=args.max_queries,
        style=args.style,
        seed=args.seed,
        batch_size=args.batch_size,
        active_corpus_ids=active_corpus_ids,
    )

    if not rows:
        raise RuntimeError(
            "No benchmark rows generated. Ensure collection payload has doc_number and dieu fields."
        )

    write_dataset(rows, output_dir=output_dir, split=args.split)

    manifest = {
        "collection": args.collection,
        "qdrant_url": args.qdrant_url,
        "split": args.split,
        "style": args.style,
        "seed": args.seed,
        "total_points_scanned": total_points,
        "payloads_missing_doc_or_dieu": skipped_invalid,
        "payloads_filtered_inactive": skipped_inactive,
        "queries_generated": len(rows),
        "output_dir": str(output_dir),
        "active_only": args.active_only,
        "query_date": args.query_date,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Generated internal benchmark: {len(rows)} queries")
    print(f"Output dir: {output_dir}")
    print(f"Queries: {output_dir / 'queries.jsonl'}")
    print(f"Qrels: {output_dir / 'qrels' / (args.split + '.jsonl')}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
