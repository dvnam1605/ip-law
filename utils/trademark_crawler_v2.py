"""
WIPO Brand DB — Crawl ALL Vietnamese Trademarks via Excel Download.
Adaptive prefix subdivision: tự chia nhỏ prefix cho đến khi mỗi query ≤ 180 kết quả.

Usage:
    python -m utils.trademark_crawler_v2 --resume
    python -m utils.trademark_crawler_v2 --count-only   # chỉ đếm tổng
"""
import asyncio
import json
import random
import logging
from collections import deque
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from playwright.async_api import async_playwright, Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
EXCEL_DIR = PROJECT_ROOT / "data" / "trademarks" / "vn_excel"
STATE_FILE = PROJECT_ROOT / "data" / "trademarks" / "vn_crawl_state.json"

# Ký tự khởi đầu: a-z, 0-9 + ký tự tiếng Việt đặc biệt
INITIAL_PREFIXES = list("abcdefghijklmnopqrstuvwxyz0123456789")
EXPAND_CHARS = list("abcdefghijklmnopqrstuvwxyz0123456789 ")

MAX_EXPORT_ROWS = 180  # WIPO giới hạn 180 records per Excel download
MAX_PREFIX_DEPTH = 4   # Không chia sâu hơn 4 ký tự


class WIPOAllVNCrawler:
    """Crawl tất cả nhãn hiệu Việt Nam từ WIPO Brand DB bằng Excel download."""

    BASE_URL = "https://branddb.wipo.int/branddb/en/"
    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, headless: bool = True):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("playwright required: pip install playwright && playwright install chromium")
        self.headless = headless
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ── Browser lifecycle ──────────────────────────────

    async def _init_browser(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            user_agent=self.USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
        )
        self._page = await self._context.new_page()

    async def _close(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    # ── CAPTCHA & IP Office ────────────────────────────

    async def _bypass_captcha(self):
        """Load WIPO & chờ altcha auto-solve."""
        logger.info("Loading WIPO Brand DB & bypassing CAPTCHA...")
        await self._page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(15)
        url = self._page.url
        if "similarname" in url or "quicksearch" in url:
            logger.info("CAPTCHA bypassed — on search page")
        else:
            logger.warning(f"Unexpected URL: {url}, waiting more...")
            await asyncio.sleep(10)

    async def _set_ip_office_vn(self):
        """Chọn IP office = (VN) IP VIET NAM qua Angular autocomplete."""
        page = self._page
        inputs = await page.query_selector_all("input.b-input__text-input")
        if len(inputs) < 5:
            raise RuntimeError(f"Expected ≥5 inputs, got {len(inputs)}")

        ip_input = inputs[3]  # IP office field
        await ip_input.click()
        await ip_input.fill("")
        for ch in "Viet":
            await page.keyboard.type(ch, delay=100)
        await asyncio.sleep(3)

        # Click autocomplete option
        vn_opt = await page.query_selector('li:has-text("(VN)")')
        if vn_opt and await vn_opt.is_visible():
            await vn_opt.click()
            logger.info("Selected IP office: (VN) IP VIET NAM")
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Cannot find VN in IP office autocomplete")

    # ── Search & Count ─────────────────────────────────

    async def _search_and_count(self, prefix: str) -> int:
        """Fill brand name, click Search, trả về tổng số kết quả."""
        page = self._page
        inputs = await page.query_selector_all("input.b-input__text-input")
        brand_input = inputs[0]

        await brand_input.click()
        await brand_input.fill("")
        await asyncio.sleep(0.2)
        await brand_input.fill(prefix)
        await asyncio.sleep(0.3)

        search_btn = await page.query_selector("button.search")
        if not search_btn:
            raise RuntimeError("Search button not found")

        disabled = await search_btn.get_attribute("disabled")
        if disabled is not None:
            logger.warning(f"Search button disabled for prefix '{prefix}'")
            return 0

        await search_btn.click()
        await asyncio.sleep(12)

        count_text = await page.evaluate("""() => {
            const body = document.body.innerText;
            const m = body.match(/of ([\\d,]+) results/);
            return m ? m[1] : '0';
        }""")
        count = int(count_text.replace(",", ""))
        logger.info(f"  prefix='{prefix}' → {count:,} results")
        return count

    # ── Excel Download ─────────────────────────────────

    async def _download_excel(self, prefix: str) -> Optional[Path]:
        """Download Excel cho kết quả hiện tại, trả về path."""
        page = self._page

        dl_btn = await page.query_selector('text=Download results')
        if not dl_btn or not await dl_btn.is_visible():
            logger.warning(f"Download button not visible for prefix '{prefix}'")
            return None

        await dl_btn.click()
        await asyncio.sleep(3)

        excel_btn = await page.query_selector('text=Excel')
        if not excel_btn:
            logger.warning(f"Excel option not found for prefix '{prefix}'")
            return None

        try:
            async with page.expect_download(timeout=60000) as dl_info:
                await excel_btn.click()
            download = await dl_info.value
            # Sanitize prefix for filename
            safe_prefix = prefix.replace(" ", "_").replace("/", "_") or "empty"
            save_path = EXCEL_DIR / f"{safe_prefix}.xlsx"
            await download.save_as(str(save_path))
            logger.info(f"  ✅ Downloaded: {save_path.name}")
            return save_path
        except Exception as e:
            logger.error(f"  Download failed for '{prefix}': {e}")
            return None

    # ── Navigation helpers ─────────────────────────────

    async def _go_back_to_search(self):
        """Quay lại trang search sau khi xem results."""
        page = self._page
        edit_btn = await page.query_selector('button:has-text("Edit your search")')
        if edit_btn and await edit_btn.is_visible():
            await edit_btn.click()
            await asyncio.sleep(3)
        else:
            await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(8)
            await self._set_ip_office_vn()

    # ── State management ───────────────────────────────

    @staticmethod
    def _load_state() -> dict:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"completed": [], "skipped": [], "failed": [], "total_downloaded": 0}

    @staticmethod
    def _save_state(state: dict):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    # ── Main crawl loop ────────────────────────────────

    async def crawl_all_vn(self, resume: bool = True, max_depth: int = MAX_PREFIX_DEPTH):
        """
        Crawl tất cả nhãn hiệu VN bằng adaptive prefix subdivision.

        Thuật toán:
          1. Queue bắt đầu: a, b, c, ..., z, 0, ..., 9
          2. Với mỗi prefix:
             - count ≤ 180 → download Excel
             - count > 180 → chia nhỏ: [prefix+a, prefix+b, ..., prefix+9]
             - count == 0 → skip
          3. Nếu prefix dài > max_depth → force download (lấy 180 đầu, có thể bị miss)
        """
        EXCEL_DIR.mkdir(parents=True, exist_ok=True)

        state = self._load_state() if resume else {"completed": [], "skipped": [], "failed": [], "total_downloaded": 0}
        completed = set(state["completed"])
        skipped = set(state.get("skipped", []))
        failed_set = set(state.get("failed", []))

        # Build queue — skip completed
        queue = deque()
        for p in INITIAL_PREFIXES:
            if p not in completed and p not in skipped:
                queue.append(p)

        logger.info(f"Starting crawl: {len(queue)} prefixes in queue, {len(completed)} already completed")

        try:
            await self._init_browser()
            await self._bypass_captcha()
            await self._set_ip_office_vn()

            while queue:
                prefix = queue.popleft()

                if prefix in completed or prefix in skipped:
                    continue

                # Check if any parent prefix was already completed
                # (e.g., if 'ab' was completed as single download, skip 'abc')
                parent_done = False
                for i in range(1, len(prefix)):
                    if prefix[:i] in completed:
                        parent_done = True
                        break
                if parent_done:
                    continue

                logger.info(f"[Queue: {len(queue)}] Processing prefix: '{prefix}'")

                try:
                    count = await self._search_and_count(prefix)
                except Exception as e:
                    logger.error(f"  Search failed for '{prefix}': {e}")
                    state["failed"].append(prefix)
                    self._save_state(state)
                    await self._go_back_to_search()
                    await asyncio.sleep(3)
                    continue

                if count == 0:
                    skipped.add(prefix)
                    state["skipped"] = list(skipped)
                    self._save_state(state)
                    await self._go_back_to_search()
                    await asyncio.sleep(1 + random.random())
                    continue

                if count <= MAX_EXPORT_ROWS or len(prefix) >= max_depth:
                    if count > MAX_EXPORT_ROWS:
                        logger.warning(f"  prefix='{prefix}' has {count} results but depth={len(prefix)} reached max — downloading top 180")

                    # Download Excel
                    retries = 3
                    downloaded = False
                    for attempt in range(retries):
                        path = await self._download_excel(prefix)
                        if path and path.exists():
                            downloaded = True
                            break
                        logger.warning(f"  Retry {attempt+1}/{retries} for '{prefix}'")
                        await asyncio.sleep(3)

                    if downloaded:
                        completed.add(prefix)
                        state["completed"] = list(completed)
                        state["total_downloaded"] = state.get("total_downloaded", 0) + 1
                    else:
                        state["failed"].append(prefix)

                    self._save_state(state)
                    await self._go_back_to_search()
                    await asyncio.sleep(2 + random.random() * 3)

                else:
                    # Subdivide: thêm mỗi ký tự expand vào queue
                    logger.info(f"  Subdividing '{prefix}' ({count:,} results) → {len(EXPAND_CHARS)} sub-prefixes")
                    for ch in EXPAND_CHARS:
                        sub = prefix + ch
                        if sub not in completed and sub not in skipped:
                            queue.append(sub)

                    await self._go_back_to_search()
                    await asyncio.sleep(1 + random.random())

        except Exception as e:
            logger.error(f"Crawl error: {e}", exc_info=True)
        finally:
            self._save_state(state)
            await self._close()

        logger.info(f"✅ Crawl complete: {len(completed)} prefixes downloaded, "
                     f"{len(skipped)} skipped (0 results), "
                     f"{len(state.get('failed', []))} failed")

    # ── Quick count ────────────────────────────────────

    async def count_all_prefixes(self):
        """Đếm nhanh số kết quả cho mỗi prefix đơn để ước lượng tổng."""
        try:
            await self._init_browser()
            await self._bypass_captcha()
            await self._set_ip_office_vn()

            total = 0
            counts = {}
            for prefix in INITIAL_PREFIXES:
                count = await self._search_and_count(prefix)
                counts[prefix] = count
                total += count
                await self._go_back_to_search()
                await asyncio.sleep(1 + random.random())

            logger.info(f"\n{'='*50}")
            logger.info(f"TỔNG ƯỚC LƯỢNG: {total:,} nhãn hiệu VN")
            logger.info(f"{'='*50}")
            for p, c in sorted(counts.items(), key=lambda x: -x[1]):
                bar = "█" * (c // 500)
                logger.info(f"  '{p}': {c:>8,}  {bar}")

            return counts, total

        finally:
            await self._close()


# ── CLI ────────────────────────────────────────────────

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Crawl ALL Vietnamese trademarks from WIPO Brand DB")
    parser.add_argument("--resume", action="store_true", default=True, help="Resume from last state")
    parser.add_argument("--fresh", action="store_true", help="Start fresh (ignore previous state)")
    parser.add_argument("--count-only", action="store_true", help="Only count results per prefix")
    parser.add_argument("--max-depth", type=int, default=MAX_PREFIX_DEPTH, help="Max prefix depth")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--visible", action="store_true", help="Show browser window")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    headless = not args.visible
    crawler = WIPOAllVNCrawler(headless=headless)

    if args.count_only:
        await crawler.count_all_prefixes()
    else:
        await crawler.crawl_all_vn(resume=not args.fresh, max_depth=args.max_depth)


if __name__ == "__main__":
    asyncio.run(main())
