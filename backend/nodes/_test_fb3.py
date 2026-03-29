"""Debug: inspeccionar el modal de login."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
if os.path.exists(env_file):
    for line in open(env_file):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from playwright.async_api import async_playwright

EMAIL = os.getenv("FB_EMAIL")
PASSWORD = os.getenv("FB_PASSWORD")

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="es-AR",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )
        page = await ctx.new_page()
        await page.goto("https://www.facebook.com/luganense", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        print("URL:", page.url)

        # Buscar inputs visibles
        inputs = await page.query_selector_all("input")
        print(f"\nInputs en la página: {len(inputs)}")
        for inp in inputs:
            itype = await inp.get_attribute("type")
            iname = await inp.get_attribute("name")
            iid   = await inp.get_attribute("id")
            iph   = await inp.get_attribute("placeholder")
            visible = await inp.is_visible()
            print(f"  type={itype!r:10} name={iname!r:15} id={iid!r:20} placeholder={iph!r:25} visible={visible}")

        # Buscar botones con texto de login
        buttons = await page.query_selector_all("button, [role='button']")
        print(f"\nBotones: {len(buttons)}")
        for btn in buttons[:15]:
            text = (await btn.inner_text()).strip()[:50]
            visible = await btn.is_visible()
            if text:
                print(f"  '{text}' visible={visible}")

asyncio.run(main())
