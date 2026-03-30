#!/usr/bin/env python3
"""
Verifica si las cookies de FB Luganense están próximas a expirar o ya expiraron.
Si hay problema: envía alerta por Telegram al admin.

Configurar en .env:
  ADMIN_CHAT_ID=<chat_id del admin — obtenelo enviando /start al bot de Luganense>

Uso:
  .venv/bin/python scripts/fb_check_cookies.py

Cron diario (desde la raíz del worktree _):
  0 9 * * * cd /Users/josetabuyo/Development/pulpo/_ && .venv/bin/python scripts/fb_check_cookies.py >> monitor/fb_cookies.log 2>&1
"""
import json
import os
import sys
import time
from pathlib import Path

# ── Configuración ─────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
COOKIES_FILE = ROOT / "data" / "sessions" / "fb-luganense" / "cookies.json"
DAYS_WARNING = 14   # avisar con N días de antelación

# Token del bot Luganense (de phones.json)
def _get_tg_token() -> str:
    try:
        phones = json.loads((ROOT / "phones.json").read_text())
        luganense = next(b for b in phones["bots"] if b.get("name") == "Luganense")
        tg = luganense.get("telegram", [])
        if isinstance(tg, list) and tg:
            return tg[0].get("token", "")
    except Exception:
        pass
    return ""


def _load_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


# ── Alertas ───────────────────────────────────────────────────────────────────

def _send_telegram(token: str, chat_id: str, msg: str) -> bool:
    try:
        import urllib.request
        import urllib.parse
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[fb_check] Error enviando Telegram: {e}")
        return False


def alert(msg: str):
    print(msg)
    token = _get_tg_token()
    chat_id = os.getenv("ADMIN_CHAT_ID", "")
    if token and chat_id:
        _send_telegram(token, chat_id, msg)
    else:
        if not token:
            print("[fb_check] Sin token Telegram — alerta solo en log")
        if not chat_id:
            print("[fb_check] ADMIN_CHAT_ID no configurado — agregar al .env")


# ── Lógica principal ──────────────────────────────────────────────────────────

def main():
    _load_env()

    if not COOKIES_FILE.exists():
        alert(
            "⚠️ [Luganense Bot] Cookies de Facebook NO ENCONTRADAS.\n"
            "El bot está usando fallback estático. Re-login requerido:\n"
            "1. rm data/sessions/fb-luganense/cookies.json (ya no existe)\n"
            "2. Enviar cualquier mensaje al bot de Luganense\n"
            "3. Chrome se abre visible → completar si pide 2FA"
        )
        sys.exit(1)

    try:
        cookies = json.loads(COOKIES_FILE.read_text())
    except Exception as e:
        alert(f"⚠️ [Luganense Bot] Error leyendo cookies FB: {e}")
        sys.exit(1)

    now = time.time()
    expirations = [c["expires"] for c in cookies if isinstance(c.get("expires"), (int, float)) and c["expires"] > 0]

    if not expirations:
        print("✅ Cookies FB Luganense sin fecha de expiración (sesión de browser) — OK por ahora.")
        sys.exit(0)

    min_exp = min(expirations)
    days_left = (min_exp - now) / 86400

    if days_left < 0:
        alert(
            f"🚨 [Luganense Bot] Cookies de Facebook EXPIRADAS hace {abs(days_left):.0f} días.\n"
            "El bot está usando fallback estático. Re-login urgente:\n"
            "1. rm data/sessions/fb-luganense/cookies.json\n"
            "2. Enviar cualquier mensaje al bot de Luganense\n"
            "3. Chrome se abre visible → completar si pide 2FA"
        )
        sys.exit(1)
    elif days_left < DAYS_WARNING:
        alert(
            f"⚠️ [Luganense Bot] Cookies de Facebook expiran en {days_left:.0f} días.\n"
            "Renovar pronto para no perder el acceso al feed."
        )
        sys.exit(0)
    else:
        print(f"✅ Cookies FB Luganense OK — expiran en {days_left:.0f} días.")
        sys.exit(0)


if __name__ == "__main__":
    main()
