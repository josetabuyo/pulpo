"""Debug: ve qué hay en la página después del login."""
import asyncio, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
if os.path.exists(env_file):
    for line in open(env_file):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from playwright.async_api import async_playwright
from pathlib import Path

COOKIES_PATH = Path(__file__).parent.parent.parent / "data" / "sessions" / "fb-luganense" / "cookies.json"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="es-AR",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )

        if COOKIES_PATH.exists():
            saved = json.loads(COOKIES_PATH.read_text())
            await ctx.add_cookies(saved)
            print(f"Cookies cargadas: {len(saved)}")

        page = await ctx.new_page()
        await page.goto("https://www.facebook.com/luganense", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        print("URL final:", page.url)

        # Screenshot
        screenshot_path = "/tmp/fb_luganense.png"
        await page.screenshot(path=screenshot_path, full_page=False)
        print("Screenshot guardado en:", screenshot_path)

        # Probar distintos selectores
        for selector in [
            "[role='article']",
            "div[data-pagelet='ProfileTimeline'] [role='article']",
            "div[role='feed'] [role='article']",
            "div[data-ad-preview='message']",
            "div[data-testid='post_message']",
        ]:
            els = await page.query_selector_all(selector)
            print(f"  {selector!r:60s} → {len(els)} elementos")

        # Texto visible largo
        body = await page.inner_text("body")
        lines = [l.strip() for l in body.split("\n") if len(l.strip()) > 40]
        print(f"\nLineas con texto (>{40} chars): {len(lines)}")
        for l in lines[:20]:
            print("  >>", l[:120])

        await browser.close()

asyncio.run(main())
