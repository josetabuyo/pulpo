"""
Script standalone para hacer login en Facebook y guardar las cookies.
Corre independiente del backend — úsalo cuando las cookies expiran.

Uso:
    cd /Users/josetabuyo/Development/pulpo/_
    python scripts/fb_login.py

Abre un browser visible. Completa el captcha o 2FA si aparece.
El browser se cierra solo cuando el login es exitoso.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# Cargar .env manualmente
_ENV_PATH = Path(__file__).parent.parent / ".env"
for line in _ENV_PATH.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

FB_EMAIL    = os.environ.get("FB_EMAIL", "")
FB_PASSWORD = os.environ.get("FB_PASSWORD", "")
PAGE_ID     = "luganense"

_SESSIONS_DIR = Path(__file__).parent.parent / "data" / "sessions"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


async def main():
    from playwright.async_api import async_playwright

    cookies_path = _SESSIONS_DIR / f"fb-{PAGE_ID}" / "cookies.json"
    cookies_path.parent.mkdir(parents=True, exist_ok=True)

    if not FB_EMAIL or not FB_PASSWORD:
        print("ERROR: FB_EMAIL o FB_PASSWORD no configurados en .env")
        sys.exit(1)

    print(f"Abriendo browser para login en Facebook...")
    print(f"  Email: {FB_EMAIL}")
    print(f"  Cookies → {cookies_path}")
    print()
    print("Si aparece captcha o 2FA, completalo en el browser.")
    print("El script espera hasta 120 segundos para que termines.")
    print()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(locale="es-AR", user_agent=_UA)
        page = await ctx.new_page()

        await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=20_000)
        await page.wait_for_timeout(1_500)
        await page.wait_for_selector("input[name='email']", timeout=15_000)
        await page.fill("input[name='email']", FB_EMAIL)
        await page.fill("input[name='pass']", FB_PASSWORD)
        await page.press("input[name='pass']", "Enter")

        print("Credenciales enviadas. Completá el captcha si aparece.")
        print("Esperando hasta 120s a que el login sea exitoso...")

        # Esperar a que aparezca c_user — el cookie que prueba sesión real en FB
        logged_in = False
        for _ in range(120):
            cookies = await ctx.cookies()
            if any(c["name"] == "c_user" for c in cookies):
                logged_in = True
                break
            await page.wait_for_timeout(1_000)

        if not logged_in:
            print("ERROR: Timeout — no se completó el login en 120 segundos.")
            await browser.close()
            sys.exit(1)

        # Un poco más para que se terminen de setear todas las cookies
        await page.wait_for_timeout(2_000)
        cookies = await ctx.cookies()

        if "login" in page.url or "checkpoint" in page.url:
            print(f"ERROR: Login falló. URL actual: {page.url}")
            await browser.close()
            sys.exit(1)

        cookies = await ctx.cookies()
        cookies_path.write_text(json.dumps(cookies, ensure_ascii=False))
        print(f"Login exitoso — {len(cookies)} cookies guardadas en:")
        print(f"  {cookies_path}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
