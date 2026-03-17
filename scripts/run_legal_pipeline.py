#!/usr/bin/env python3
"""
Legal Document Pipeline — Chunk → Qdrant + Neo4j in one run.

Combines:
  1. chunking/legal_chunker.py    (TXT → Qdrant + JSON metadata)
  2. utils/neo4j_ingest.py        (JSON → Neo4j graph)

Usage:
  python scripts/run_legal_pipeline.py                   # full pipeline
  python scripts/run_legal_pipeline.py --skip-ingest     # chỉ chunk + Qdrant
  python scripts/run_legal_pipeline.py --skip-chunk      # chỉ ingest Neo4j (dùng JSON có sẵn)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

# ── Ensure project root is importable ──────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)

# ── Paths ──────────────────────────────────────────────
TXT_FOLDER = PROJECT_ROOT / "data" / "processed" / "phap-luat"
EMBEDDING_MODEL_PATH = PROJECT_ROOT / "data" / "models" / "vietnamese_embedding"
CHUNKS_JSON = PROJECT_ROOT / "chunking" / "chunks_output_v2.json"


# ═══════════════════════════════════════════════════════
#  STEP 1: Chunking → Qdrant + metadata JSON
# ═══════════════════════════════════════════════════════
def run_chunking():
    """Chunk legal TXT files, upload to Qdrant, save metadata JSON."""
    from backend.chunking.legal_chunker import (
        EmbeddingModel, QdrantStorage, process_txt,
        analyze_chunks, print_analysis,
        QDRANT_URL, LEGAL_COLLECTION,
    )

    print("=" * 60)
    print("📄 STEP 1: LEGAL DOCUMENT CHUNKING → QDRANT")
    print("=" * 60)

    txt_folder = TXT_FOLDER if TXT_FOLDER.exists() else PROJECT_ROOT
    txt_files = sorted(txt_folder.glob("*.txt"))
    if not txt_files:
        print(f"❌ Không tìm thấy file TXT trong {txt_folder}")
        return False

    print(f"📂 Tìm thấy {len(txt_files)} file TXT trong {txt_folder}")

    embedding_model = EmbeddingModel(str(EMBEDDING_MODEL_PATH))
    vector_size = embedding_model.get_dimension()

    all_results = []
    for txt_file in txt_files:
        results = process_txt(str(txt_file), embedding_model)
        all_results.extend(results)

    print(f"\n{'=' * 60}")
    print(f"TỔNG KẾT: {len(all_results)} chunks từ {len(txt_files)} files")
    stats = analyze_chunks(all_results)
    print_analysis(stats)

    # Save metadata-only JSON (for Neo4j ingest)
    json_data = [{"content": r["content"], "metadata": r["metadata"]} for r in all_results]
    CHUNKS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(CHUNKS_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"💾 Exported {len(json_data)} chunks → {CHUNKS_JSON}")

    # Upload to Qdrant directly
    print(f"\n🔄 Uploading to Qdrant ({QDRANT_URL})...")
    storage = QdrantStorage(QDRANT_URL, LEGAL_COLLECTION, vector_size)
    count = storage.upsert_results(all_results)
    print(f"✅ Uploaded {count} vectors to Qdrant '{LEGAL_COLLECTION}'")

    return True


# ═══════════════════════════════════════════════════════
#  STEP 2: Neo4j Ingest (metadata + graph only)
# ═══════════════════════════════════════════════════════
def run_ingest():
    """Ingest chunks into Neo4j (no embeddings — those are in Qdrant)."""
    from backend.tooling.neo4j_ingest import (
        Neo4jClient, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_AVAILABLE,
        setup_schema, load_chunks, ingest_documents, ingest_chunks,
        create_next_relationships, get_stats,
    )

    print("\n" + "=" * 60)
    print("🗄️  STEP 2: NEO4J INGEST (metadata + graph)")
    print("=" * 60)

    if not NEO4J_AVAILABLE:
        print("❌ neo4j package not installed. Run: pip install neo4j")
        return False

    print(f"🔌 Connecting to Neo4j at {NEO4J_URI}...")
    try:
        client = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return False

    try:
        setup_schema(client)
        chunks = load_chunks(str(CHUNKS_JSON))
        docs = ingest_documents(client, chunks)
        ingest_chunks(client, chunks, docs)
        create_next_relationships(client)

        get_stats(client)
        print("\n✅ NEO4J INGEST COMPLETE!")
        return True
    except Exception as e:
        print(f"❌ Ingest error: {e}")
        return False
    finally:
        client.close()


# ═══════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Legal Document Pipeline: Chunk → Qdrant + Neo4j"
    )
    parser.add_argument("--skip-chunk", action="store_true", help="Bỏ qua bước chunk (dùng JSON đã có)")
    parser.add_argument("--skip-ingest", action="store_true", help="Bỏ qua bước ingest Neo4j")
    args = parser.parse_args()

    print("🏛️  LEGAL DOCUMENT PIPELINE")
    print("=" * 60)
    start = time.time()

    if not args.skip_chunk:
        if not run_chunking():
            sys.exit(1)
    else:
        print("⏭️  Skipping chunking (--skip-chunk)")
        if not CHUNKS_JSON.exists():
            print(f"❌ Chunks JSON not found: {CHUNKS_JSON}")
            sys.exit(1)

    if not args.skip_ingest:
        if not run_ingest():
            sys.exit(1)
    else:
        print("⏭️  Skipping ingest (--skip-ingest)")

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"🎉 LEGAL PIPELINE HOÀN TẤT — {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
