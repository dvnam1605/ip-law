#!/usr/bin/env python3
"""
Master Pipeline — Chạy tất cả hoặc chọn pipeline.

Usage:
  python scripts/run_all_pipelines.py                                # legal + verdict
  python scripts/run_all_pipelines.py --legal                        # chỉ legal
  python scripts/run_all_pipelines.py --verdict                      # chỉ verdict
  python scripts/run_all_pipelines.py --trademark -k "Samsung"       # chỉ trademark
  python scripts/run_all_pipelines.py --all -k "Samsung" "Apple"     # tất cả
  python scripts/run_all_pipelines.py --skip-chunk                   # skip chunk cho legal+verdict
  python scripts/run_all_pipelines.py --skip-ingest                  # skip ingest cho tất cả
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def run_script(name: str, args: list) -> bool:
    """Run a pipeline script as a subprocess, streaming output."""
    script = SCRIPTS_DIR / name
    cmd = [sys.executable, str(script)] + args
    print(f"\n{'━' * 60}")
    print(f"▶ Running: {' '.join(cmd)}")
    print(f"{'━' * 60}\n")

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Master Pipeline: chạy tất cả pipeline một lần",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  %(prog)s                                  # legal + verdict (mặc định)
  %(prog)s --legal                          # chỉ legal
  %(prog)s --verdict                        # chỉ verdict
  %(prog)s --trademark -k Samsung Apple     # chỉ trademark
  %(prog)s --vn-trademark                   # crawl ALL VN trademarks
  %(prog)s --all -k Samsung                 # tất cả
  %(prog)s --skip-chunk                     # legal+verdict chỉ ingest
        """,
    )

    group = parser.add_argument_group("Pipeline selection")
    group.add_argument("--legal", action="store_true", help="Chạy Legal pipeline")
    group.add_argument("--verdict", action="store_true", help="Chạy Verdict pipeline")
    group.add_argument("--trademark", action="store_true", help="Chạy Trademark pipeline")
    group.add_argument("--vn-trademark", action="store_true", help="Crawl ALL VN trademarks pipeline")
    group.add_argument("--all", action="store_true", help="Chạy tất cả pipeline")

    parser.add_argument("--skip-chunk", action="store_true", help="Bỏ qua bước chunk/crawl")
    parser.add_argument("--skip-ingest", action="store_true", help="Bỏ qua bước ingest Neo4j")

    tm_group = parser.add_argument_group("Trademark options")
    tm_group.add_argument("-k", "--keywords", nargs="+", help="Keywords cho trademark crawl")
    tm_group.add_argument("--country", default="VN", help="Country code (mặc định: VN)")
    tm_group.add_argument("--pages", type=int, default=3, help="Max pages per keyword")
    tm_group.add_argument("--tm-input", default=None, help="Input JSON cho trademark (nếu skip-crawl)")

    args = parser.parse_args()

    # Default: legal + verdict if nothing specified
    run_legal = args.legal or args.all
    run_verdict = args.verdict or args.all
    run_trademark = args.trademark or args.all
    run_vn_trademark = args.vn_trademark or args.all

    if not (args.legal or args.verdict or args.trademark or args.vn_trademark or args.all):
        run_legal = True
        run_verdict = True

    print("🚀 MASTER PIPELINE")
    print("=" * 60)
    pipelines = []
    if run_legal:
        pipelines.append("Legal")
    if run_verdict:
        pipelines.append("Verdict")
    if run_trademark:
        pipelines.append("Trademark")
    if run_vn_trademark:
        pipelines.append("VN-Trademark")
    print(f"   Pipelines: {', '.join(pipelines)}")
    print("=" * 60)

    start = time.time()
    results = {}

    # ── Legal ──────────────────────────────────────────
    if run_legal:
        extra_args = []
        if args.skip_chunk:
            extra_args.append("--skip-chunk")
        if args.skip_ingest:
            extra_args.append("--skip-ingest")
        ok = run_script("run_legal_pipeline.py", extra_args)
        results["Legal"] = "✅" if ok else "❌"
        if not ok:
            print("⚠️  Legal pipeline failed, continuing...")

    # ── Verdict ────────────────────────────────────────
    if run_verdict:
        extra_args = []
        if args.skip_chunk:
            extra_args.append("--skip-chunk")
        if args.skip_ingest:
            extra_args.append("--skip-ingest")
        ok = run_script("run_verdict_pipeline.py", extra_args)
        results["Verdict"] = "✅" if ok else "❌"
        if not ok:
            print("⚠️  Verdict pipeline failed, continuing...")

    # ── Trademark ──────────────────────────────────────
    if run_trademark:
        extra_args = []
        if args.skip_chunk:
            if not args.tm_input:
                print("❌ Trademark --skip-crawl requires --tm-input <json>")
                results["Trademark"] = "❌"
            else:
                extra_args.extend(["--skip-crawl", "--input", args.tm_input])
        else:
            if not args.keywords:
                print("❌ Trademark pipeline requires -k <keywords>")
                results["Trademark"] = "❌"
            else:
                extra_args.extend(args.keywords)
                extra_args.extend(["--country", args.country, "--pages", str(args.pages)])

        if args.skip_ingest:
            extra_args.append("--skip-ingest")

        if "Trademark" not in results:  # not already failed
            ok = run_script("run_trademark_pipeline.py", extra_args)
            results["Trademark"] = "✅" if ok else "❌"

    # ── VN Trademark ───────────────────────────────────
    if run_vn_trademark:
        extra_args = []
        if args.skip_chunk:
            extra_args.append("--skip-crawl")
        if args.skip_ingest:
            extra_args.append("--skip-ingest")
        ok = run_script("run_vn_trademark_pipeline.py", extra_args)
        results["VN-Trademark"] = "✅" if ok else "❌"
        if not ok:
            print("⚠️  VN Trademark pipeline failed, continuing...")

    # ── Summary ────────────────────────────────────────
    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print("📊 KẾT QUẢ TỔNG HỢP")
    print(f"{'=' * 60}")
    for name, status in results.items():
        print(f"   {status} {name}")
    print(f"\n⏱  Tổng thời gian: {elapsed:.1f}s")

    all_ok = all(s == "✅" for s in results.values())
    if all_ok:
        print("🎉 TẤT CẢ PIPELINE HOÀN TẤT!")
    else:
        print("⚠️  Một số pipeline thất bại, xem log ở trên.")
        sys.exit(1)


if __name__ == "__main__":
    main()
