#!/usr/bin/env python3
"""
Verdict Pipeline — Chunk → Qdrant + Neo4j in one run.

Combines:
  1. chunking/verdict_chunker.py       (TXT → Qdrant + JSON metadata)
  2. utils/verdict_neo4j_ingest.py     (JSON → Neo4j graph)

Usage:
  python scripts/run_verdict_pipeline.py                   # full pipeline
  python scripts/run_verdict_pipeline.py --skip-ingest     # chỉ chunk + Qdrant
  python scripts/run_verdict_pipeline.py --skip-chunk      # chỉ ingest Neo4j
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
TXT_FOLDER = PROJECT_ROOT / "data" / "processed" / "ban-an"
CHUNKS_JSON = PROJECT_ROOT / "chunking" / "verdict_chunks.json"


# ═══════════════════════════════════════════════════════
#  STEP 1: Chunking → Qdrant + metadata JSON
# ═══════════════════════════════════════════════════════
def run_chunking():
    """Chunk verdict TXT files, upload to Qdrant, save metadata JSON."""
    from backend.chunking.verdict_chunker import (
        chunk_all_verdicts, generate_embeddings, export_json,
        QdrantVerdictStorage, QDRANT_URL, VERDICT_COLLECTION,
    )

    print("=" * 60)
    print("⚖️  STEP 1: VERDICT CHUNKING → QDRANT")
    print("=" * 60)

    if not TXT_FOLDER.exists():
        print(f"❌ Thư mục bản án không tồn tại: {TXT_FOLDER}")
        return False

    chunks = chunk_all_verdicts(str(TXT_FOLDER))
    if not chunks:
        print("❌ Không tạo được chunk nào!")
        return False

    # Save metadata-only JSON (for Neo4j ingest)
    export_json(chunks, str(CHUNKS_JSON))

    # Generate embeddings and upload to Qdrant directly
    data = generate_embeddings(chunks)
    print(f"\n🔄 Uploading to Qdrant ({QDRANT_URL})...")
    storage = QdrantVerdictStorage(QDRANT_URL, VERDICT_COLLECTION)
    count = storage.upsert_results(data)
    print(f"✅ Uploaded {count} vectors to Qdrant '{VERDICT_COLLECTION}'")

    print("✅ Chunking hoàn tất!")
    return True


# ═══════════════════════════════════════════════════════
#  STEP 2: Neo4j Ingest (metadata + graph only)
# ═══════════════════════════════════════════════════════
def run_ingest():
    """Ingest verdict chunks into Neo4j (no embeddings)."""
    from backend.utils.verdict_neo4j_ingest import (
        Neo4jClient, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
        setup_schema, load_chunks, ingest_verdicts, ingest_verdict_chunks,
        create_next_relationships, create_semantic_relationships,
        print_stats,
    )

    print("\n" + "=" * 60)
    print("🗄️  STEP 2: NEO4J VERDICT INGEST (metadata + graph)")
    print("=" * 60)

    print(f"🔌 Connecting to Neo4j at {NEO4J_URI}...")
    try:
        client = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return False

    try:
        setup_schema(client)
        chunks = load_chunks(str(CHUNKS_JSON))
        verdicts = ingest_verdicts(client, chunks)
        ingest_verdict_chunks(client, chunks, verdicts)
        create_next_relationships(client)
        create_semantic_relationships(client)

        print_stats(client)
        print("\n✅ VERDICT INGEST COMPLETE!")
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
        description="Verdict Pipeline: Chunk → Qdrant + Neo4j"
    )
    parser.add_argument("--skip-chunk", action="store_true", help="Bỏ qua bước chunk (dùng JSON đã có)")
    parser.add_argument("--skip-ingest", action="store_true", help="Bỏ qua bước ingest Neo4j")
    args = parser.parse_args()

    print("⚖️  VERDICT PIPELINE")
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
    print(f"🎉 VERDICT PIPELINE HOÀN TẤT — {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
