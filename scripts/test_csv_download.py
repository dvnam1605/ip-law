"""
Test WIPO Brand DB API - Phase 4: Intercept full request/response to understand API format.
"""
import asyncio
import json
import logging
from pathlib import Path

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path(__file__).parent.parent / "data" / "trademarks" / "csv_test"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://branddb.wipo.int/branddb/en/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


async def test_vn_filter_and_download():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        accept_downloads=True,
    )
    page = await context.new_page()

    # Intercept search API request body and response
    search_requests = []
    search_responses = []

    async def on_route(route):
        url = route.request.url
        if 'api.branddb.wipo.int/search' in url:
            # Capture request details
            body = route.request.post_data
            headers = dict(route.request.headers)
            search_requests.append({
                'url': url,
                'method': route.request.method,
                'body': body,
                'headers': headers,
            })
        await route.continue_()

    await page.route('**/*', on_route)

    # Also capture response
    async def on_response(response):
        if 'api.branddb.wipo.int/search' in response.url:
            try:
                body = await response.text()
                search_responses.append({
                    'url': response.url,
                    'status': response.status,
                    'headers': dict(response.headers),
                    'body': body[:5000],
                })
            except Exception as e:
                search_responses.append({'error': str(e)})

    page.on('response', on_response)

    # ── Step 1: Bypass CAPTCHA ──
    logger.info("Step 1: Bypassing CAPTCHA...")
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(15)

    # ── Step 2: Fill IP office = VN + brand 'a' + Search ──
    logger.info("Step 2: Setting IP office = VN + brand = 'a' + Search...")
    inputs = await page.query_selector_all("input.b-input__text-input")

    # IP office
    await inputs[3].click()
    await inputs[3].fill("")
    for char in "Viet":
        await page.keyboard.type(char, delay=100)
    await asyncio.sleep(3)
    vn_opt = await page.query_selector('li:has-text("(VN)")')
    if vn_opt:
        await vn_opt.click()
        await asyncio.sleep(1)

    # Brand name
    await inputs[0].click()
    await inputs[0].fill("a")
    await asyncio.sleep(0.5)

    # Search
    search_btn = await page.query_selector("button.search")
    if search_btn:
        await search_btn.click()
        logger.info("Clicked Search")
        await asyncio.sleep(15)

    # ── Step 3: Analyze captured API data ──
    logger.info(f"\nStep 3: Captured {len(search_requests)} search requests:")
    for i, req in enumerate(search_requests):
        logger.info(f"\n--- Request [{i}] ---")
        logger.info(f"  URL: {req['url']}")
        logger.info(f"  Method: {req['method']}")
        logger.info(f"  Body: {req['body']}")
        # Show relevant headers
        for h in ['hashsearch', 'content-type', 'accept', 'authorization', 'cookie']:
            if h in req['headers']:
                logger.info(f"  Header {h}: {req['headers'][h]}")

    logger.info(f"\nCaptured {len(search_responses)} search responses:")
    for i, resp in enumerate(search_responses):
        logger.info(f"\n--- Response [{i}] ---")
        logger.info(f"  Status: {resp.get('status')}")
        logger.info(f"  Content-Type: {resp.get('headers', {}).get('content-type', 'unknown')}")
        body = resp.get('body', '')
        logger.info(f"  Body length: {len(body)}")
        # Try to parse as JSON
        try:
            data = json.loads(body)
            logger.info(f"  JSON keys: {list(data.keys()) if isinstance(data, dict) else 'array'}")
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, (int, str, float, bool)):
                        logger.info(f"    {k}: {v}")
                    elif isinstance(v, list):
                        logger.info(f"    {k}: list[{len(v)}]")
                        if v and isinstance(v[0], dict):
                            logger.info(f"    {k}[0] keys: {list(v[0].keys())}")
                            # Show first item
                            logger.info(f"    {k}[0]: {json.dumps(v[0], ensure_ascii=False)[:500]}")
                    elif isinstance(v, dict):
                        logger.info(f"    {k}: dict with keys {list(v.keys())[:10]}")
        except json.JSONDecodeError:
            logger.info(f"  Body preview (not JSON): {body[:500]}")

    # ── Step 4: Save full API data to file for analysis ──
    api_data_path = str(DOWNLOAD_DIR / "api_capture.json")
    with open(api_data_path, "w", encoding="utf-8") as f:
        json.dump({
            "requests": search_requests,
            "responses": [
                {k: v for k, v in r.items() if k != 'body'}
                for r in search_responses
            ],
            "response_bodies": [r.get('body', '') for r in search_responses],
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"\nSaved API capture to: {api_data_path}")

    # ── Step 5: Try direct API call with custom pagination ──
    logger.info("\nStep 5: Testing direct API call with custom rows...")
    if search_requests:
        req = search_requests[0]
        hash_search = req['headers'].get('hashsearch', '')
        logger.info(f"  Using hashsearch: {hash_search}")

        # Try fetching with rows=500 to test if we can get more than 30
        for rows in [100, 500, 1000]:
            result = await page.evaluate(f"""async () => {{
                try {{
                    const body = {req['body']};
                    body.rows = {rows};
                    body.start = 0;
                    const r = await fetch('https://api.branddb.wipo.int/search', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'Accept': 'application/json, text/plain, */*',
                            'hashsearch': '{hash_search}',
                        }},
                        body: JSON.stringify(body),
                    }});
                    const data = await r.json();
                    return {{
                        status: r.status,
                        total: data.total || data.numFound || data.count || 'unknown',
                        returned: data.docs ? data.docs.length : (data.results ? data.results.length : 'unknown'),
                        keys: Object.keys(data),
                    }};
                }} catch(e) {{
                    return {{ error: e.message }};
                }}
            }}""")
            logger.info(f"  rows={rows}: {result}")

    # ── Step 6: Test VN-only (no brand name) via API ──
    logger.info("\nStep 6: Testing VN-only API call (no brand name filter)...")
    if search_requests:
        req = search_requests[0]
        hash_search = req['headers'].get('hashsearch', '')

        result_vn = await page.evaluate(f"""async () => {{
            try {{
                const body = {{
                    rows: 5,
                    start: 0,
                    sort: "score desc",
                    asStructure: {{
                        boolean: "AND",
                        bricks: [
                            {{key: "office", value: [{{value: "VN"}}], strategy: "any_of"}}
                        ]
                    }}
                }};
                const r = await fetch('https://api.branddb.wipo.int/search', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Accept': 'application/json, text/plain, */*',
                        'hashsearch': '{hash_search}',
                    }},
                    body: JSON.stringify(body),
                }});
                const data = await r.json();
                return {{
                    status: r.status,
                    total: data.total || data.numFound || data.count || 'unknown',
                    returned: data.docs ? data.docs.length : (data.results ? data.results.length : 'unknown'),
                    keys: Object.keys(data),
                    firstDoc: data.docs ? JSON.stringify(data.docs[0]).substring(0, 500) : 'no docs',
                }};
            }} catch(e) {{
                return {{ error: e.message }};
            }}
        }}""")
        logger.info(f"  VN-only result: {result_vn}")

    await browser.close()
    await pw.stop()
    logger.info("✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(test_vn_filter_and_download())
