"""
WIPO Brand DB Batch Crawler
Crawls registered trademarks from WIPO Global Brand Database.
Uses Playwright to bypass altcha CAPTCHA and scrape Angular-rendered DOM.
"""
import asyncio
import json
import random
import logging
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

try:
    from playwright.async_api import async_playwright, Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CRAWL_OUTPUT_DIR = PROJECT_ROOT / "data" / "trademarks"


@dataclass
class TrademarkRecord:
    brand_name: str
    owner_name: str
    owner_country: str = ""
    registration_number: str = ""
    nice_classes: List[str] = None
    ipr_type: str = ""
    country_of_filing: str = ""
    status: str = ""
    status_date: str = ""
    wipo_url: str = ""
    crawled_at: str = ""

    def __post_init__(self):
        if self.nice_classes is None:
            self.nice_classes = []
        if not self.crawled_at:
            self.crawled_at = datetime.utcnow().isoformat()


class WIPOBrandDBCrawler:
    """Crawl trademarks from WIPO Global Brand Database (branddb.wipo.int)."""

    BASE_URL = "https://branddb.wipo.int/branddb/en/"
    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    RESULTS_PER_PAGE = 30

    def __init__(self, headless: bool = True):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("playwright is required: pip install playwright && playwright install chromium")
        self.headless = headless
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def _init_browser(self):
        """Launch browser and create context."""
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            user_agent=self.USER_AGENT,
            viewport={"width": 1920, "height": 1080},
        )
        self._page = await self._context.new_page()

    async def _close(self):
        if self._browser:
            await self._browser.close()

    async def _bypass_captcha(self):
        """Load WIPO Brand DB and wait for altcha proof-of-work CAPTCHA to auto-solve."""
        logger.info("Loading WIPO Brand DB & bypassing CAPTCHA...")
        await self._page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=30000)
        # altcha auto="onload" will self-solve; wait for redirect to search page
        await asyncio.sleep(15)
        url = self._page.url
        if "similarname" in url or "quicksearch" in url:
            logger.info("CAPTCHA bypassed — on search page")
        else:
            logger.warning(f"Unexpected URL after CAPTCHA wait: {url}")
            await asyncio.sleep(10)

    async def _search(self, brand_name: str, country: str = "VN"):
        """Fill search form and click Search."""
        page = self._page

        # Fill brand name (first .b-input__text-input)
        inputs = await page.query_selector_all("input.b-input__text-input")
        if not inputs:
            raise RuntimeError("Cannot find search input fields")

        brand_input = inputs[0]
        await brand_input.click()
        await brand_input.fill(brand_name)
        logger.info(f"Search: brand_name='{brand_name}'")

        await asyncio.sleep(0.5)

        # Click Search button
        search_btn = await page.query_selector("button.search")
        if search_btn:
            await search_btn.click()
        else:
            await brand_input.press("Enter")

        # Wait for results to render
        logger.info("Waiting for results to render...")
        await asyncio.sleep(12)

    def _parse_owner(self, raw: str) -> tuple:
        """Parse owner string like 'Samsung Electronics Co. (Korea (Republic of))' -> (name, country)."""
        if "(" in raw:
            idx = raw.rfind("(")
            name = raw[:idx].strip()
            country = raw[idx:].strip("() ")
            return name, country
        return raw.strip(), ""

    async def _scrape_current_page(self) -> List[TrademarkRecord]:
        """Scrape trademark records from the currently rendered results page."""
        page = self._page
        records = []

        # Scroll down repeatedly to force Angular to render all items (virtual scroll)
        for _ in range(15):
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(0.4)
        # Scroll back to top
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        # Extract data using JS — parse innerText blocks from each result card
        data = await page.evaluate("""() => {
            // Try to find individual result card elements first
            const cardSelectors = [
                '[class*="result"] [class*="card"]',
                '[class*="result-item"]',
                '.b-result-item',
                'result-item',
                '[class*="result"] > div > div',
            ];

            // Fallback: parse from full text
            const body = document.body.innerText;
            const lines = body.split('\\n').map(l => l.trim()).filter(l => l);
            const startIdx = lines.findIndex(l => /Displaying \\d+-\\d+ of [\\d,]+ results/.test(l));
            if (startIdx === -1) return { resultLines: [], resultCount: '0' };
            const countMatch = lines[startIdx].match(/of ([\\d,]+) results/);
            return {
                resultLines: lines.slice(startIdx + 1),
                resultCount: countMatch ? countMatch[1] : '0'
            };
        }""")

        result_lines = data.get("resultLines", [])
        result_count = data.get("resultCount", "0")
        logger.info(f"Total results: {result_count}, lines on page: {len(result_lines)}")

        # Parse structured lines: pattern repeats as:
        # [brand_name], "Owner", [owner], "Nice class", [classes...], "IPR", [ipr_type],
        # "Country of filing", [country], "Status", [status_line], "Number", [number]
        i = 0
        skip_prefixes = (
            "Results view", "Change layout", "Sort results", "Results per page",
            "Download results", "Filters", "Select all", "Statistics view",
            "List", "Grid", "Gallery",
        )

        while i < len(result_lines):
            line = result_lines[i]

            # Skip UI chrome
            if any(line.startswith(s) for s in skip_prefixes):
                i += 1
                continue

            # Detect start of a trademark record: brand name followed by "Owner"
            if i + 1 < len(result_lines) and result_lines[i + 1] == "Owner":
                rec = TrademarkRecord(brand_name=line, owner_name="")
                i += 2  # skip brand_name + "Owner"

                # Parse remaining fields until next brand (next "Owner" keyword or end)
                while i < len(result_lines):
                    curr = result_lines[i]

                    if curr == "Nice class":
                        i += 1
                        # Collect nice class numbers (could be multi-line)
                        classes = []
                        while i < len(result_lines) and result_lines[i] not in ("IPR", "Owner", "Nice class"):
                            # Nice classes are numbers, possibly comma-separated
                            parts = result_lines[i].replace(",", " ").split()
                            for p in parts:
                                if p.isdigit():
                                    classes.append(p)
                                else:
                                    break
                            if not any(p.isdigit() for p in parts):
                                break
                            i += 1
                        rec.nice_classes = classes
                        continue

                    elif curr == "IPR":
                        i += 1
                        if i < len(result_lines):
                            rec.ipr_type = result_lines[i]
                            i += 1
                        continue

                    elif curr == "Country of filing":
                        i += 1
                        if i < len(result_lines):
                            rec.country_of_filing = result_lines[i]
                            i += 1
                        continue

                    elif curr == "Status":
                        i += 1
                        if i < len(result_lines):
                            rec.status = result_lines[i]
                            # Extract date from status like "Registered (March 19, 1998)"
                            if "(" in rec.status and ")" in rec.status:
                                date_part = rec.status[rec.status.index("(") + 1:rec.status.index(")")]
                                rec.status_date = date_part
                            i += 1
                        continue

                    elif curr == "Number":
                        i += 1
                        if i < len(result_lines):
                            rec.registration_number = result_lines[i]
                            i += 1
                        # Record complete
                        break

                    elif curr == "Owner":
                        # Next record starts — don't consume
                        break

                    else:
                        # Owner name (first unrecognized field after brand)
                        if not rec.owner_name:
                            name, country = self._parse_owner(curr)
                            rec.owner_name = name
                            rec.owner_country = country
                        i += 1
                        continue

                records.append(rec)
            else:
                i += 1

        logger.info(f"Scraped {len(records)} records from current page")
        return records

    async def _go_next_page(self) -> bool:
        """Click next page button. Returns True if navigation succeeded."""
        page = self._page
        next_btn = await page.query_selector('button[aria-label="Next"], button:has-text("navigate_next")')
        if not next_btn:
            # Try alternative selector
            next_btn = await page.query_selector('.b-pagination__next, .b-navigation__button--next')

        if next_btn:
            disabled = await next_btn.get_attribute("disabled")
            if disabled is not None:
                return False
            await next_btn.click()
            await asyncio.sleep(8)
            return True
        return False

    async def crawl(
        self,
        brand_name: str,
        country: str = "VN",
        max_pages: int = 5,
    ) -> List[TrademarkRecord]:
        """
        Crawl trademarks matching brand_name in the given country.

        Args:
            brand_name: Trademark name to search
            country: Designation country code (default: VN)
            max_pages: Maximum pages to crawl (30 results/page)

        Returns:
            List of TrademarkRecord
        """
        all_records = []

        try:
            await self._init_browser()
            await self._bypass_captcha()
            await self._search(brand_name, country)

            for page_num in range(1, max_pages + 1):
                logger.info(f"Scraping page {page_num}/{max_pages}...")
                records = await self._scrape_current_page()
                all_records.extend(records)

                if page_num < max_pages:
                    has_next = await self._go_next_page()
                    if not has_next:
                        logger.info("No more pages")
                        break
                    # Random delay to be polite
                    delay = 2 + random.random() * 2
                    await asyncio.sleep(delay)

        except Exception as e:
            logger.error(f"Crawl error: {e}", exc_info=True)
        finally:
            await self._close()

        logger.info(f"Total records crawled: {len(all_records)}")
        return all_records

    async def crawl_batch(
        self,
        keywords: List[str],
        country: str = "VN",
        max_pages_per_keyword: int = 3,
        output_file: Optional[str] = None,
    ) -> List[TrademarkRecord]:
        """
        Crawl multiple keywords sequentially.

        Args:
            keywords: List of brand names to search
            country: Designation country
            max_pages_per_keyword: Max pages per keyword
            output_file: Optional JSON output file path

        Returns:
            Combined list of TrademarkRecord
        """
        all_records = []

        try:
            await self._init_browser()
            await self._bypass_captcha()

            for idx, keyword in enumerate(keywords, 1):
                logger.info(f"[{idx}/{len(keywords)}] Crawling '{keyword}'...")

                await self._search(keyword, country)

                for page_num in range(1, max_pages_per_keyword + 1):
                    records = await self._scrape_current_page()
                    all_records.extend(records)

                    if page_num < max_pages_per_keyword:
                        has_next = await self._go_next_page()
                        if not has_next:
                            break
                        await asyncio.sleep(2 + random.random() * 2)

                # Delay between keywords
                if idx < len(keywords):
                    delay = 3 + random.random() * 3
                    await asyncio.sleep(delay)

                    # Navigate back to search page for next keyword
                    await self._page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Batch crawl error: {e}", exc_info=True)
        finally:
            await self._close()

        # Deduplicate by registration_number
        seen = set()
        unique_records = []
        for rec in all_records:
            key = f"{rec.brand_name}:{rec.registration_number}"
            if key not in seen:
                seen.add(key)
                unique_records.append(rec)

        logger.info(f"Total unique records: {len(unique_records)} (from {len(all_records)} raw)")

        # Save to file
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump([asdict(r) for r in unique_records], f, ensure_ascii=False, indent=2)
            logger.info(f"Saved to {output_path}")

        return unique_records


# ── CLI Entry Point ──────────────────────────────────

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Crawl trademarks from WIPO Brand DB")
    parser.add_argument("keywords", nargs="+", help="Brand names to search")
    parser.add_argument("--country", default="VN", help="Designation country (default: VN)")
    parser.add_argument("--pages", type=int, default=3, help="Max pages per keyword")
    parser.add_argument("--output", "-o", default=None, help="Output JSON file")
    parser.add_argument("--headless", action="store_true", default=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    output = args.output or str(CRAWL_OUTPUT_DIR / f"trademarks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    crawler = WIPOBrandDBCrawler(headless=args.headless)
    records = await crawler.crawl_batch(
        keywords=args.keywords,
        country=args.country,
        max_pages_per_keyword=args.pages,
        output_file=output,
    )

    print(f"\n✅ Crawled {len(records)} unique trademarks → {output}")


if __name__ == "__main__":
    asyncio.run(main())
