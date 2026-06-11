"""
Debug interactivo de audios WA Web — browser VISIBLE.

Abre el mismo Chrome de la sesión WA en modo visible. El usuario navega,
clickea play en los audios. Cada blob reproducido se captura, transcribe
y muestra en terminal.

USO (desde la raíz del worktree):
  1. Detener el backend:
       ./stop-backend.sh

  2. Correr con el Python del venv:
       ../.venv/bin/python3 backend/tools/debug_audio.py 5491155612767
       ../.venv/bin/python3 backend/tools/debug_audio.py 5491155612767 "Desarrollo SIGIRH  2025"

     El nombre del grupo/contacto es opcional — si lo ponés abre ese chat automáticamente.

  3. En el browser: clickear play en los audios que quieras transcribir.
     La transcripción aparece en la terminal con el contexto del mensaje.

  4. Al terminar: Ctrl+C, luego reiniciar backend:
       ./restart-backend.sh

IMPORTANTE: el backend debe estar detenido (stop-backend.sh) antes de correr este
script — Chrome no puede compartir el mismo perfil con dos procesos.
"""
import asyncio
import base64
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = BACKEND_DIR / "data" / "sessions"

_INTERCEPTOR_JS = """
(function() {
    if (window.__pulpo_debug_installed) return 'already';
    window.__pulpo_debug_installed = true;
    window.__pulpo_blobs = [];
    window.__pulpo_seen = new Set();

    const orig = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {
        set(url) {
            if (url && url.startsWith('blob:') && !window.__pulpo_seen.has(url)) {
                window.__pulpo_seen.add(url);
                let prePlain = '';
                let el = this;
                while (el && el !== document.body) {
                    if (el.getAttribute('data-pre-plain-text')) {
                        prePlain = el.getAttribute('data-pre-plain-text'); break;
                    }
                    const found = el.querySelector('[data-pre-plain-text]');
                    if (found) { prePlain = found.getAttribute('data-pre-plain-text'); break; }
                    el = el.parentElement;
                }
                window.__pulpo_blobs.push({ url, prePlain, ts: Date.now() });
            }
            if (orig?.set) orig.set.call(this, url);
        },
        get() { return orig?.get ? orig.get.call(this) : undefined; },
        configurable: true,
    });
    return 'installed';
})()
"""

_DRAIN_JS = "() => { const b = window.__pulpo_blobs || []; window.__pulpo_blobs = []; return b; }"

_FETCH_BLOB_JS = """
async (url) => {
    try {
        const r = await fetch(url);
        const buf = await r.arrayBuffer();
        const b = new Uint8Array(buf);
        let s = '';
        for (let x of b) s += String.fromCharCode(x);
        return btoa(s);
    } catch(e) { return null; }
}
"""

_OPEN_CHAT_JS = """
(name) => {
    const norm = s => s.replace(/[\\u00a0\\u202a\\u202c\\u200e\\u200f]/g,' ').trim();
    const grid = document.querySelector('[role="grid"]');
    if (!grid) return false;
    for (const s of grid.querySelectorAll('span[title]')) {
        if (norm(s.getAttribute('title')) === norm(name)) {
            s.click(); return true;
        }
    }
    return false;
}
"""


async def transcribe_blob(page, blob_url: str) -> str | None:
    b64 = await page.evaluate(_FETCH_BLOB_JS, blob_url)
    if not b64:
        return None
    data = base64.b64decode(b64)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from tools.transcription import transcribe
        return await transcribe(tmp)
    except Exception as e:
        print(f"  [error] {e}")
        return None
    finally:
        Path(tmp).unlink(missing_ok=True)


async def run(session_id: str, contact_name: str | None):
    from playwright.async_api import async_playwright

    profile_dir = SESSIONS_DIR / session_id / "profile"
    sys.path.insert(0, str(BACKEND_DIR))
    if not profile_dir.exists():
        print(f"ERROR: perfil no encontrado: {profile_dir}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  PULPO — Debug Audio (browser visible)")
    print(f"  Sesión: {session_id}")
    if contact_name:
        print(f"  Abriendo: {contact_name}")
    print(f"{'='*60}\n")

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
            locale="es-AR",
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        if "web.whatsapp.com" not in page.url:
            await page.goto("https://web.whatsapp.com")

        print("Esperando WA Web...", end="", flush=True)
        try:
            await page.wait_for_selector("[role='grid']", timeout=30000)
            print(" ✓")
        except Exception:
            print(" (sin panel de chats — puede necesitar QR)")

        status = await page.evaluate(_INTERCEPTOR_JS)
        print(f"Interceptor: {status}\n")

        if contact_name:
            ok = await page.evaluate(_OPEN_CHAT_JS, contact_name)
            if ok:
                await page.wait_for_timeout(1500)
                await page.evaluate(_INTERCEPTOR_JS)
                print(f"Chat '{contact_name}' abierto.\n")
            else:
                print(f"  [aviso] No encontré '{contact_name}' en la lista — abrílo manualmente.\n")

        print("─" * 60)
        print("Clickeá play en los audios. Ctrl+C para terminar.")
        print("─" * 60)

        results = []
        try:
            while True:
                await asyncio.sleep(1)
                try:
                    installed = await page.evaluate("() => !!window.__pulpo_debug_installed")
                    if not installed:
                        await page.evaluate(_INTERCEPTOR_JS)
                except Exception:
                    continue

                blobs = await page.evaluate(_DRAIN_JS)
                for b in blobs:
                    url = b.get("url", "")
                    pre = b.get("prePlain", "")
                    print(f"\n🎵 Blob capturado ({time.strftime('%H:%M:%S')})")
                    if pre:
                        print(f"   {pre.strip()}")
                    print("   Transcribiendo...", end="", flush=True)

                    text = await transcribe_blob(page, url)
                    if text:
                        print(f"\r   ✅ {text}")
                        results.append({"prePlain": pre, "text": text})
                    else:
                        print(f"\r   ❌ blob expirado o error")
                    print()

        except KeyboardInterrupt:
            print(f"\n\n{'='*60}")
            print(f"  {len(results)} audio(s) transcripto(s).")
            for i, r in enumerate(results, 1):
                print(f"  [{i}] {r['text'][:100]}")
            print(f"{'='*60}")
            print("\nCerrando...\nDespués: ./restart-backend.sh\n")

        await ctx.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
