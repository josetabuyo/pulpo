"""
Login interactivo a Facebook — corre UNA vez para guardar cookies.
Modo visible para que puedas aprobar 2FA o captchas si aparecen.

Uso:
    /Users/josetabuyo/Development/pulpo/_/backend/.venv/bin/python nodes/_login_fb.py
"""
import asyncio, json, os, sys
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

EMAIL    = os.getenv("FB_EMAIL")
PASSWORD = os.getenv("FB_PASSWORD")
COOKIES_PATH = Path(__file__).parent.parent.parent / "data" / "sessions" / "fb-luganense" / "cookies.json"


async def main():
    print(f"Email: {EMAIL}")
    print(f"Guardando cookies en: {COOKIES_PATH}")
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(
            locale="es-AR",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = await ctx.new_page()

        # Ir directo al login page (no al modal)
        print("Navegando a facebook.com/login ...")
        await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)

        # Llenar formulario de login
        print("Llenando email y contraseña ...")
        await page.fill("input[name='email']", EMAIL)
        await page.fill("input[name='pass']", PASSWORD)
        await page.press("input[name='pass']", "Enter")
        await page.wait_for_timeout(4000)

        print(f"URL después del login: {page.url}")

        # Si hay checkpoint/2FA, esperar automáticamente hasta 90 seg a que el usuario lo resuelva
        if "checkpoint" in page.url or "two_step" in page.url or "login" in page.url:
            print()
            print("⚠️  Se requiere verificación adicional (2FA / captcha).")
            print("    Resolvela en el browser abierto. Esperando hasta 90 segundos...")
            for i in range(45):
                await page.wait_for_timeout(2000)
                current_url = page.url
                if "two_step" not in current_url and "checkpoint" not in current_url and "login" not in current_url:
                    print(f"    ✅ Verificación completada. URL: {current_url}")
                    break
                print(f"    Esperando... ({(i+1)*2}s) URL: {current_url[:60]}")
            else:
                print("    ⏱  Timeout esperando verificación.")

        # Verificar que estamos logueados
        await page.goto("https://www.facebook.com/luganense", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Contar artículos visibles como señal de login exitoso
        articles = await page.query_selector_all("[role='article']")
        print(f"\nArtículos visibles en la página de Luganense: {len(articles)}")

        # Guardar cookies
        cookies = await ctx.cookies()
        COOKIES_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
        print(f"✅ Cookies guardadas: {len(cookies)} cookies en {COOKIES_PATH}")

        # Mostrar preview de posts
        if articles:
            print("\n--- Preview de posts encontrados ---")
            for i, art in enumerate(articles[:3]):
                text = await art.inner_text()
                lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 30]
                if lines:
                    print(f"\nPost {i+1}:")
                    print("\n".join(lines[:4]))

        await browser.close()
        print("\nListo. Ahora el scraper headless usará estas cookies.")

asyncio.run(main())
