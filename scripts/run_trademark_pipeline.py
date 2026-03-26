#!/usr/bin/env python3
"""
Trademark Pipeline — Crawl WIPO + Ingest to PostgreSQL in one run.

Combines:
    1. backend.tooling.trademark_crawler     (WIPO -> JSON)
    2. backend.tooling.trademark_pg_ingest    (JSON -> PostgreSQL)

Usage:
  python scripts/run_trademark_pipeline.py "Samsung" "Apple"
  python scripts/run_trademark_pipeline.py "Nike" --country VN --pages 5
  python scripts/run_trademark_pipeline.py --skip-crawl --input data/trademarks/existing.json
  python scripts/run_trademark_pipeline.py "Brand" --skip-ingest
"""
import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Ensure project root is importable ──────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# sys.path no longer needed
os.chdir(PROJECT_ROOT)

# ── Paths ──────────────────────────────────────────────
CRAWL_OUTPUT_DIR = PROJECT_ROOT / "data" / "trademarks"


# ═══════════════════════════════════════════════════════
#  STEP 1: Crawl
# ═══════════════════════════════════════════════════════
async def run_crawl(keywords: list, country: str, pages: int, output_file: str) -> str:
    """Crawl trademarks from WIPO Brand DB."""
    from backend.tooling.trademark_crawler import WIPOBrandDBCrawler

    print("=" * 60)
    print("🌐 STEP 1: CRAWL WIPO BRAND DB")
    print("=" * 60)
    print(f"   Keywords: {keywords}")
    print(f"   Country:  {country}")
    print(f"   Pages:    {pages} per keyword")

    crawler = WIPOBrandDBCrawler(headless=True)
    records = await crawler.crawl_batch(
        keywords=keywords,
        country=country,
        max_pages_per_keyword=pages,
        output_file=output_file,
    )

    print(f"\n✅ Crawled {len(records)} trademarks → {output_file}")
    return output_file


# ═══════════════════════════════════════════════════════
#  STEP 2: PostgreSQL Ingest
# ═══════════════════════════════════════════════════════
async def run_ingest(input_file: str, batch_size: int = 50):
    """Ingest crawled trademarks into PostgreSQL."""
    from backend.tooling.trademark_pg_ingest import TrademarkPGIngestor

    print("\n" + "=" * 60)
    print("🗄️  STEP 2: POSTGRESQL TRADEMARK INGEST")
    print("=" * 60)

    if not Path(input_file).exists():
        print(f"❌ Input file not found: {input_file}")
        return False

    try:
        ingestor = TrademarkPGIngestor()
    except Exception as e:
        print(f"❌ Failed to initialize ingestor: {e}")
        return False

    try:
        await ingestor.ingest_from_file(input_file, batch_size)
        count = await ingestor.get_count()
        print(f"\n✅ TRADEMARK INGEST COMPLETE! Total: {count} trademarks")
        return True
    except Exception as e:
        print(f"❌ Ingest error: {e}")
        return False
    finally:
        await ingestor.close()


# ═══════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Trademark Pipeline: Crawl WIPO -> Ingest PostgreSQL"
    )
    parser.add_argument("keywords", nargs="*", help="Brand names to search on WIPO")
    parser.add_argument("--country", default="VN", help="Country code (default: VN)")
    parser.add_argument("--pages", type=int, default=3, help="Max pages per keyword (default: 3)")
    parser.add_argument("--input", "-i", default=None, help="Input JSON file (for --skip-crawl)")
    parser.add_argument("--output", "-o", default=None, help="Output JSON file for crawl results")
    parser.add_argument("--batch-size", type=int, default=50, help="PostgreSQL ingest batch size")
    parser.add_argument("--skip-crawl", action="store_true", help="Bỏ qua crawl (dùng --input)")
    parser.add_argument("--skip-ingest", action="store_true", help="Bỏ qua ingest Neo4j")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("🏷️  TRADEMARK PIPELINE")
    print("=" * 60)
    start = time.time()

    # Determine output file path
    output_file = args.output or str(
        CRAWL_OUTPUT_DIR / f"trademarks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    input_file = args.input or output_file

    # Step 1: Crawl
    if not args.skip_crawl:
        if not args.keywords:
            parser.error("Cần ít nhất 1 keyword, ví dụ: python scripts/run_trademark_pipeline.py 'Samsung'")
        CRAWL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        input_file = asyncio.run(run_crawl(args.keywords, args.country, args.pages, output_file))
    else:
        print("⏭️  Skipping crawl (--skip-crawl)")
        if not args.input:
            parser.error("--skip-crawl requires --input <json file>")

    # Step 2: Ingest
    if not args.skip_ingest:
        if not asyncio.run(run_ingest(input_file, args.batch_size)):
            sys.exit(1)
    else:
        print("⏭️  Skipping ingest (--skip-ingest)")

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"🎉 TRADEMARK PIPELINE HOÀN TẤT — {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
