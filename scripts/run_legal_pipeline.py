#!/usr/bin/env python3
"""
Legal Document Pipeline — Chunk + Ingest to Neo4j in one run.

Combines:
  1. chunking/legal_chunker_v2.py  (TXT → JSON with embeddings)
  2. utils/neo4j_ingest.py         (JSON → Neo4j)

Usage:
  python scripts/run_legal_pipeline.py                   # full pipeline
  python scripts/run_legal_pipeline.py --skip-ingest     # chỉ chunk
  python scripts/run_legal_pipeline.py --skip-chunk      # chỉ ingest (dùng JSON có sẵn)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

# ── Ensure project root is importable ──────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

# ── Paths ──────────────────────────────────────────────
TXT_FOLDER = PROJECT_ROOT / "output"
EMBEDDING_MODEL_PATH = PROJECT_ROOT / "vietnamese_embedding"
CHUNKS_JSON = PROJECT_ROOT / "chunking" / "chunks_output_v2.json"
EMBEDDINGS_JSON = PROJECT_ROOT / "chunking" / "chunks_output_v2_with_embeddings.json"


# ═══════════════════════════════════════════════════════
#  STEP 1: Chunking
# ═══════════════════════════════════════════════════════
def run_chunking():
    """Chunk legal TXT files and generate embeddings."""
    from chunking.legal_chunker_v2 import (
        EmbeddingModel, process_txt_v2, analyze_chunks, print_analysis,
    )

    print("=" * 60)
    print("📄 STEP 1: LEGAL DOCUMENT CHUNKING")
    print("=" * 60)

    txt_folder = TXT_FOLDER if TXT_FOLDER.exists() else PROJECT_ROOT
    txt_files = sorted(txt_folder.glob("*.txt"))
    if not txt_files:
        print(f"❌ Không tìm thấy file TXT trong {txt_folder}")
        return False

    print(f"📂 Tìm thấy {len(txt_files)} file TXT trong {txt_folder}")

    model_path = EMBEDDING_MODEL_PATH
    if not model_path.exists():
        model_path = PROJECT_ROOT / "vietnamese_embedding"
    embedding_model = EmbeddingModel(str(model_path))

    all_results = []
    for txt_file in txt_files:
        results = process_txt_v2(str(txt_file), embedding_model)
        all_results.extend(results)

    print(f"\n{'=' * 60}")
    print(f"TỔNG KẾT: {len(all_results)} chunks từ {len(txt_files)} files")
    stats = analyze_chunks(all_results)
    print_analysis(stats)

    # Export JSON (metadata only)
    json_data = [{"content": r["content"], "metadata": r["metadata"]} for r in all_results]
    CHUNKS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(CHUNKS_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"💾 Exported {len(json_data)} chunks → {CHUNKS_JSON}")

    # Export JSON (with embeddings)
    with open(EMBEDDINGS_JSON, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False)
    size_mb = EMBEDDINGS_JSON.stat().st_size / (1024 * 1024)
    print(f"💾 Exported {len(all_results)} chunks+embeddings → {EMBEDDINGS_JSON} ({size_mb:.1f} MB)")

    return True


# ═══════════════════════════════════════════════════════
#  STEP 2: Neo4j Ingest
# ═══════════════════════════════════════════════════════
def run_ingest():
    """Ingest chunks + embeddings into Neo4j."""
    from utils.neo4j_ingest import (
        Neo4jClient, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_AVAILABLE,
        setup_schema, load_chunks, ingest_documents, ingest_chunks,
        create_next_relationships, setup_vector_index, ingest_embeddings,
        get_stats,
    )

    print("\n" + "=" * 60)
    print("🗄️  STEP 2: NEO4J INGEST")
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
        setup_vector_index(client, dimension=1024)

        if EMBEDDINGS_JSON.exists():
            ingest_embeddings(client, str(EMBEDDINGS_JSON))
        else:
            print(f"⚠️ Embeddings file not found: {EMBEDDINGS_JSON}")

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
        description="Legal Document Pipeline: Chunk → Ingest Neo4j"
    )
    parser.add_argument("--skip-chunk", action="store_true", help="Bỏ qua bước chunk (dùng JSON đã có)")
    parser.add_argument("--skip-ingest", action="store_true", help="Bỏ qua bước ingest Neo4j")
    args = parser.parse_args()

    print("🏛️  LEGAL DOCUMENT PIPELINE")
    print("=" * 60)
    start = time.time()

    # Step 1: Chunking
    if not args.skip_chunk:
        if not run_chunking():
            sys.exit(1)
    else:
        print("⏭️  Skipping chunking (--skip-chunk)")
        if not CHUNKS_JSON.exists():
            print(f"❌ Chunks JSON not found: {CHUNKS_JSON}")
            sys.exit(1)

    # Step 2: Ingest
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
