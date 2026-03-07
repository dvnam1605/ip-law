#!/usr/bin/env python3
"""
VN Trademark Pipeline — Crawl ALL Vietnamese trademarks + Merge + Ingest PostgreSQL.

Combines:
  1. utils/trademark_crawler_v2.py     (WIPO → Excel files, adaptive prefix subdivision)
  2. utils/xlsx_merger.py              (Excel files → deduplicated JSON)
  3. utils/trademark_pg_ingest.py      (JSON → PostgreSQL with pg_trgm)

Usage:
  python scripts/run_vn_trademark_pipeline.py                    # full pipeline (resume crawl)
  python scripts/run_vn_trademark_pipeline.py --fresh            # crawl from scratch
  python scripts/run_vn_trademark_pipeline.py --count-only       # chỉ đếm tổng nhãn hiệu VN
  python scripts/run_vn_trademark_pipeline.py --skip-crawl       # chỉ merge + ingest
  python scripts/run_vn_trademark_pipeline.py --skip-ingest      # chỉ crawl + merge
  python scripts/run_vn_trademark_pipeline.py --skip-crawl --skip-merge --input data/trademarks/all_vn_trademarks.json
"""
import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# ── Ensure project root is importable ──────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

EXCEL_DIR = PROJECT_ROOT / "data" / "trademarks" / "vn_excel"
MERGED_JSON = PROJECT_ROOT / "data" / "trademarks" / "all_vn_trademarks.json"

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
#  STEP 1: Crawl all VN trademarks (adaptive Excel download)
# ═══════════════════════════════════════════════════════
async def run_crawl(fresh: bool, max_depth: int, headless: bool):
    from utils.trademark_crawler_v2 import WIPOAllVNCrawler

    print("=" * 60)
    print("🌐 STEP 1: CRAWL ALL VN TRADEMARKS FROM WIPO")
    print("=" * 60)
    print(f"   Mode:      {'fresh' if fresh else 'resume'}")
    print(f"   Max depth: {max_depth}")
    print(f"   Excel dir: {EXCEL_DIR}")

    crawler = WIPOAllVNCrawler(headless=headless)
    await crawler.crawl_all_vn(resume=not fresh, max_depth=max_depth)

    xlsx_count = len(list(EXCEL_DIR.glob("*.xlsx"))) if EXCEL_DIR.exists() else 0
    print(f"\n✅ Crawl complete — {xlsx_count} Excel files in {EXCEL_DIR}")


# ═══════════════════════════════════════════════════════
#  STEP 1b: Count only (no download)
# ═══════════════════════════════════════════════════════
async def run_count_only(headless: bool):
    from utils.trademark_crawler_v2 import WIPOAllVNCrawler

    print("=" * 60)
    print("📊 COUNT ONLY: ước lượng tổng nhãn hiệu VN")
    print("=" * 60)

    crawler = WIPOAllVNCrawler(headless=headless)
    await crawler.count_all_prefixes()


# ═══════════════════════════════════════════════════════
#  STEP 2: Merge Excel files → JSON
# ═══════════════════════════════════════════════════════
def run_merge(input_dir: Path, output_path: Path) -> str:
    from utils.xlsx_merger import merge_all

    print("\n" + "=" * 60)
    print("📑 STEP 2: MERGE EXCEL FILES → JSON")
    print("=" * 60)
    print(f"   Input dir:  {input_dir}")
    print(f"   Output:     {output_path}")

    records = merge_all(input_dir, output_path)
    print(f"\n✅ Merged {len(records)} unique trademarks → {output_path}")
    return str(output_path)


# ═══════════════════════════════════════════════════════
#  STEP 3: PostgreSQL Ingest
# ═══════════════════════════════════════════════════════
async def run_ingest(input_file: str, batch_size: int):
    from utils.trademark_pg_ingest import TrademarkPGIngestor

    print("\n" + "=" * 60)
    print("🗄️  STEP 3: POSTGRESQL TRADEMARK INGEST")
    print("=" * 60)
    print(f"   Input:      {input_file}")
    print(f"   Batch size: {batch_size}")

    if not Path(input_file).exists():
        print(f"❌ Input file not found: {input_file}")
        return False

    try:
        ingestor = TrademarkPGIngestor()
        await ingestor.setup()
    except Exception as e:
        print(f"❌ Failed to initialize ingestor: {e}")
        return False

    try:
        await ingestor.ingest_from_file(input_file, batch_size)
        count = await ingestor.get_count()
        print(f"\n✅ POSTGRESQL INGEST COMPLETE! Total: {count} trademarks")
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
        description="VN Trademark Pipeline: Crawl ALL VN → Merge Excel → Ingest PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  %(prog)s                          # full pipeline (resume crawl)
  %(prog)s --fresh                  # crawl từ đầu
  %(prog)s --count-only             # chỉ đếm tổng
  %(prog)s --skip-crawl             # merge + ingest (đã crawl rồi)
  %(prog)s --skip-ingest            # crawl + merge only
  %(prog)s --skip-crawl --skip-merge --input all_vn.json   # chỉ ingest
        """,
    )

    parser.add_argument("--fresh", action="store_true", help="Crawl từ đầu (xóa state cũ)")
    parser.add_argument("--count-only", action="store_true", help="Chỉ đếm tổng nhãn hiệu VN, không download")
    parser.add_argument("--max-depth", type=int, default=4, help="Độ sâu tối đa khi chia prefix (default: 4)")
    parser.add_argument("--skip-crawl", action="store_true", help="Bỏ qua bước crawl")
    parser.add_argument("--skip-merge", action="store_true", help="Bỏ qua bước merge Excel")
    parser.add_argument("--skip-ingest", action="store_true", help="Bỏ qua bước ingest PostgreSQL")
    parser.add_argument("--input", "-i", type=Path, default=None, help="Input JSON (cho skip-crawl + skip-merge)")
    parser.add_argument("--excel-dir", type=Path, default=EXCEL_DIR, help="Thư mục chứa Excel files")
    parser.add_argument("--output", "-o", type=Path, default=MERGED_JSON, help="Output JSON sau merge")
    parser.add_argument("--batch-size", type=int, default=500, help="PostgreSQL batch size (default: 500)")
    parser.add_argument("--no-headless", action="store_true", help="Hiển thị browser (debug)")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    headless = not args.no_headless

    print("🏷️  VN TRADEMARK PIPELINE")
    print("=" * 60)
    start = time.time()

    # ── Count only mode ────────────────────────────────
    if args.count_only:
        asyncio.run(run_count_only(headless))
        elapsed = time.time() - start
        print(f"\n⏱  Thời gian: {elapsed:.1f}s")
        return

    # ── Step 1: Crawl ─────────────────────────────────
    if not args.skip_crawl:
        asyncio.run(run_crawl(args.fresh, args.max_depth, headless))
    else:
        print("⏭️  Skipping crawl (--skip-crawl)")

    # ── Step 2: Merge ─────────────────────────────────
    input_file = str(args.output)
    if not args.skip_merge:
        input_file = run_merge(args.excel_dir, args.output)
    else:
        print("⏭️  Skipping merge (--skip-merge)")
        if args.input:
            input_file = str(args.input)
        elif args.output.exists():
            input_file = str(args.output)
        else:
            print("❌ Không tìm thấy file JSON. Dùng --input hoặc chạy merge trước.")
            sys.exit(1)

    # ── Step 3: Ingest ────────────────────────────────
    if not args.skip_ingest:
        if not asyncio.run(run_ingest(input_file, args.batch_size)):
            sys.exit(1)
    else:
        print("⏭️  Skipping ingest (--skip-ingest)")

    # ── Summary ───────────────────────────────────────
    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"🎉 VN TRADEMARK PIPELINE HOÀN TẤT — {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
