"""
Test standalone de fetch_facebook.
Correr con: /Users/josetabuyo/Development/pulpo/_/backend/.venv/bin/python nodes/_test_fb.py
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Cargar .env manualmente
env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
if os.path.exists(env_file):
    for line in open(env_file):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from nodes.fetch_facebook import fetch


async def main():
    print("=== Test fetch_facebook ===")
    print(f"FB_EMAIL configurado: {'SI' if os.getenv('FB_EMAIL') else 'NO'}")
    print(f"FB_PASSWORD configurado: {'SI' if os.getenv('FB_PASSWORD') else 'NO'}")
    print()

    print("--- Scraping últimos posts (sin query) ---")
    content = await fetch("luganense")
    if content:
        print(f"Contenido obtenido ({len(content)} chars):")
        print(content[:800])
    else:
        print("Sin contenido — revisar credenciales o logs")

asyncio.run(main())
