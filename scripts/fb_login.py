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
    "Chrome/136.0.0.0 Safari/537.36"
)

_SUSPICIOUS_URL_FRAGMENTS = ("login", "checkpoint", "index.php", "recover", "secure", "suspended", "hacked")
_PAUSE_ON_SUSPICIOUS = 90


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
    print("El script espera hasta 180 segundos para que termines.")
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

        print("Credenciales enviadas. Completá el captcha o verificación que aparezca.")
        print("Sin límite de tiempo — el script espera hasta que termines.")
        print("Las cookies se guardan automáticamente cuando el login esté completo.")
        print()

        # Esperar sin límite a que aparezca c_user
        tick = 0
        while True:
            cookies = await ctx.cookies()
            if any(c["name"] == "c_user" for c in cookies):
                break
            await asyncio.sleep(1)
            tick += 1
            if tick % 30 == 0:
                print(f"  ... esperando login ({tick}s) — completá el captcha en el browser")

        # Intentar cerrar el aviso de "comportamiento automatizado" si aparece
        try:
            await page.get_by_text("Descartar", exact=True).click(timeout=5_000)
            print("ℹ️  Aviso de Facebook cerrado automáticamente (botón Descartar).")
        except Exception:
            pass  # el aviso no apareció, seguir normal

        # Guardar cookies inmediatamente
        cookies_path.write_text(json.dumps(cookies, ensure_ascii=False))
        print(f"\n✅ Cookies guardadas ({len(cookies)} cookies):")
        print(f"   {cookies_path}")
        print()
        print("═" * 60)
        print("⚠️  MIRÁ EL BROWSER AHORA:")
        print("   ¿Facebook muestra algún aviso, advertencia o mensaje?")
        print("   ¿Algo sobre 'actividad inusual', 'revisión' o 'suspensión'?")
        print("   Tenés 30 segundos mínimos para leerlo antes de continuar.")
        print("═" * 60)

        # Espera mínima para que el usuario pueda leer mensajes de FB
        for i in range(30, 0, -1):
            print(f"  {i:2d}s ...", end="\r", flush=True)
            await asyncio.sleep(1)
        print("  ✅ Tiempo mínimo cumplido. Podés cerrar el browser cuando quieras.")
        print()

        # Esperar a que el usuario cierre el browser
        while browser.is_connected():
            await asyncio.sleep(1)

        print("Browser cerrado. ¡Listo!")


if __name__ == "__main__":
    asyncio.run(main())
