#!/usr/bin/env python3
"""Script de debug: fetch Facebook con screenshot para ver qué ve el headless."""
import asyncio
import os
import sys
from pathlib import Path

# Entorno
os.environ["FB_DEBUG"] = "1"
os.environ.setdefault("FB_EMAIL", "jtabuyo@hotmail.com")
# FB_PASSWORD se lee del .env

root = Path(__file__).parent.parent
sys.path.insert(0, str(root / "backend"))

# Cargar .env
env_file = root / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

async def main():
    from nodes import fetch_facebook

    query = sys.argv[1] if len(sys.argv) > 1 else "milanesas"
    print(f"[debug] Buscando: '{query}' en luganense con headless...")

    # Llamar _load directamente para ver solo lo que saca el headless (sin _STATIC_POSTS)
    headless_content = await fetch_facebook._load("luganense", query)
    print(f"\n[debug] Headless raw ({len(headless_content)} chars):")
    print(headless_content[:800] if headless_content else "(vacío — nada extraído del headless)")

    static = fetch_facebook._STATIC_POSTS.get("luganense", [])
    print(f"\n[debug] Static posts: {len(static)} post(s) disponibles")
    print(f"\n[debug] Screenshot guardado en data/debug/")

asyncio.run(main())
