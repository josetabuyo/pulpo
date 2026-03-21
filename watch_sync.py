"""
Watcher de full-sync: espera que el archivo .md del grupo se actualice
y anuncia el resultado con voz via Paulina.
Uso: python watch_sync.py
"""
import os
import re
import subprocess
import sys
import time

SUMMARY = (
    "/Users/josetabuyo/Development/pulpo/_/data/summaries"
    "/la_piquiteria/Desarrollo SIGIRH\xa0\xa02025.md"
)
TIMEOUT = 600  # 10 minutos

try:
    initial_mtime = os.path.getmtime(SUMMARY)
    initial_size  = os.path.getsize(SUMMARY)
except FileNotFoundError:
    initial_mtime = 0
    initial_size  = 0

print(f"[watcher] Esperando sync... mtime={initial_mtime:.0f} size={initial_size}", flush=True)
subprocess.run(["say", "-v", "Paulina", "Watcher activo, esperando full sync"])

start = time.time()
while time.time() - start < TIMEOUT:
    try:
        mtime = os.path.getmtime(SUMMARY)
        size  = os.path.getsize(SUMMARY)
        if mtime != initial_mtime:
            with open(SUMMARY, encoding="utf-8") as f:
                content = f.read()

            n_text  = content.count("**[text]**")
            n_audio = content.count("**[audio]**")
            total   = n_text + n_audio

            # Último timestamp en el archivo
            timestamps = re.findall(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", content, re.M)
            last_ts = timestamps[-1] if timestamps else "desconocido"

            msg = (
                f"Full sync completado. "
                f"{total} mensajes en el resumen: {n_text} de texto y {n_audio} de audio. "
                f"Último mensaje: {last_ts}."
            )
            print(f"[watcher] {msg}", flush=True)
            print(f"[watcher] size={size}", flush=True)
            subprocess.run(["say", "-v", "Paulina", msg])
            sys.exit(0)
    except Exception as e:
        print(f"[watcher] Error: {e}", flush=True)
    time.sleep(3)

subprocess.run(["say", "-v", "Paulina", "Timeout. El sync tardó más de diez minutos."])
sys.exit(1)
