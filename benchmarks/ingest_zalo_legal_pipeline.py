import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Set

from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest Zalo legal retrieval corpus into Qdrant+Neo4j for pipeline benchmark")
    parser.add_argument("--data-dir", default="/home/namdv/shtt/data/zalo_ai_retrieval")
    parser.add_argument("--split", default="test")
    parser.add_argument("--collection", default="bench_zalo_legal")
    parser.add_argument("--model-path", default="/home/namdv/shtt/data/models/vietnamese_embedding")
    parser.add_argument("--qdrant-url", default="http://192.168.1.199:6333")
    parser.add_argument("--neo4j-uri", default="bolt://127.0.0.1:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="dvnam1605")
    parser.add_argument("--full-corpus", action="store_true", help="Ingest full corpus.jsonl instead of qrels-only subset")
    parser.add_argument("--recreate", action="store_true", help="Recreate target Qdrant collection")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--device", default="cpu", help="Embedding device: cpu, cuda, cuda:0 ...")
    return parser.parse_args()


def load_target_ids(data_dir: Path, split: str, full_corpus: bool) -> Set[str]:
    if full_corpus:
        ids = set()
        with (data_dir / "corpus.jsonl").open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    ids.add(row["_id"])
        return ids

    ids = set()
    with (data_dir / "qrels" / f"{split}.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                ids.add(row["corpus-id"])
    return ids


def parse_corpus_row(corpus_id: str, title: str, text: str) -> Dict:
    # corpus_id format: doc_number+dieu_index, e.g. 100/2019/nđ-cp+5
    if "+" not in corpus_id:
        return {
            "chunk_id": corpus_id,
            "doc_number": corpus_id,
            "dieu": None,
            "dieu_title": title or "",
            "content": text or "",
            "doc_name": corpus_id,
            "doc_type": "Văn bản pháp luật",
        }

    doc_number, dieu_num = corpus_id.rsplit("+", 1)
    dieu_num = dieu_num.strip().lower()
    dieu = f"Điều {dieu_num}"

    dieu_title = title or ""
    # Normalize title if it starts with Điều X.
    m = re.match(r"^\s*Điều\s+\d+[a-z]?\.?\s*(.*)$", dieu_title, flags=re.IGNORECASE)
    if m:
        dieu_title = m.group(1).strip()

    return {
        "chunk_id": corpus_id,
        "doc_number": doc_number,
        "dieu": dieu,
        "dieu_title": dieu_title,
        "content": text or "",
        "doc_name": doc_number,
        "doc_type": "Văn bản pháp luật",
    }


def load_corpus_subset(data_dir: Path, target_ids: Set[str]) -> List[Dict]:
    records = []
    with (data_dir / "corpus.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            cid = row["_id"]
            if cid not in target_ids:
                continue
            records.append(parse_corpus_row(cid, row.get("title", ""), row.get("text", "")))
    return records


def ingest_qdrant(
    records: List[Dict],
    collection: str,
    model_path: str,
    qdrant_url: str,
    recreate: bool,
    batch_size: int,
    device: str,
) -> int:
    model = SentenceTransformer(model_path, device=device)
    dim = model.get_sentence_embedding_dimension()
    client = QdrantClient(url=qdrant_url)

    if recreate:
        try:
            client.delete_collection(collection)
        except Exception:
            pass

    existing = {c.name for c in client.get_collections().collections}
    if collection not in existing:
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

    total = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        texts = [r["content"] for r in batch]
        vecs = model.encode(texts, show_progress_bar=False).tolist()
        points = []
        for j, (r, v) in enumerate(zip(batch, vecs), start=i):
            points.append(
                PointStruct(
                    id=j,
                    vector=v,
                    payload={
                        "chunk_id": r["chunk_id"],
                        "doc_number": r["doc_number"],
                        "dieu": r["dieu"],
                        "dieu_title": r["dieu_title"],
                        "doc_name": r["doc_name"],
                        "doc_type": r["doc_type"],
                        "effective_date": None,
                    },
                )
            )
        client.upsert(collection_name=collection, points=points)
        total += len(points)

    return total


def ingest_neo4j(records: List[Dict], uri: str, user: str, password: str) -> None:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    docs = {}
    for r in records:
        dn = r["doc_number"]
        if dn not in docs:
            docs[dn] = {
                "doc_id": dn,
                "doc_number": dn,
                "doc_name": r["doc_name"],
                "doc_type": r["doc_type"],
                "status": "active",
                "effective_date": None,
                "source": "zalo_benchmark",
            }

    chunks = []
    for idx, r in enumerate(records):
        chunks.append(
            {
                "chunk_id": r["chunk_id"],
                "doc_id": r["doc_number"],
                "content": r["content"],
                "chunk_index": idx,
                "chunk_type": "content",
                "dieu": r["dieu"],
                "dieu_title": r["dieu_title"],
            }
        )

    with driver.session() as session:
        session.run(
            """
            UNWIND $docs AS doc
            MERGE (d:Document {doc_id: doc.doc_id})
            SET d.doc_number = doc.doc_number,
                d.doc_name = doc.doc_name,
                d.doc_type = doc.doc_type,
                d.status = doc.status,
                d.effective_date = doc.effective_date,
                d.source = doc.source,
                d.updated_at = datetime()
            """,
            {"docs": list(docs.values())},
        )

        session.run(
            """
            UNWIND $chunks AS chunk
            MERGE (c:Chunk {chunk_id: chunk.chunk_id})
            SET c.doc_id = chunk.doc_id,
                c.content = chunk.content,
                c.chunk_index = chunk.chunk_index,
                c.chunk_type = chunk.chunk_type,
                c.dieu = chunk.dieu,
                c.dieu_title = chunk.dieu_title,
                c.updated_at = datetime()
            WITH c, chunk
            MATCH (d:Document {doc_id: chunk.doc_id})
            MERGE (c)-[:PART_OF]->(d)
            """,
            {"chunks": chunks},
        )

    driver.close()


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)

    target_ids = load_target_ids(data_dir, args.split, args.full_corpus)
    records = load_corpus_subset(data_dir, target_ids)

    if not records:
        raise RuntimeError("No corpus records matched target IDs.")

    q_count = ingest_qdrant(
        records,
        collection=args.collection,
        model_path=args.model_path,
        qdrant_url=args.qdrant_url,
        recreate=args.recreate,
        batch_size=args.batch_size,
        device=args.device,
    )
    ingest_neo4j(records, args.neo4j_uri, args.neo4j_user, args.neo4j_password)

    print(f"Ingested records: {len(records)}")
    print(f"Qdrant collection: {args.collection}")
    print(f"Qdrant upserts: {q_count}")
    print("Neo4j sync: done")


if __name__ == "__main__":
    main()
