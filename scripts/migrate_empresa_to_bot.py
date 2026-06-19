#!/usr/bin/env python3
"""
Migración DB: empresa_id → bot_id en todas las tablas.
Requiere SQLite 3.35+ (incluido en macOS Monterey+).

Correr ANTES de reiniciar el servidor con el código refactorizado.
Hace backup automático antes de migrar.
"""

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "messages.db"

MIGRATIONS = [
    # (tabla, índice_viejo, índice_nuevo)
    ("flows",               "idx_flows_empresa_id",          "idx_flows_bot_id"),
    ("contact_suggestions", "idx_contact_suggestions_empresa", "idx_contact_suggestions_bot"),
    ("jobs",                "idx_jobs_empresa_id",           "idx_jobs_bot_id"),
    ("google_connections",  "idx_google_connections_empresa", "idx_google_connections_bot"),
]


def main():
    if not DB_PATH.exists():
        print(f"DB no encontrada: {DB_PATH}")
        sys.exit(1)

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.parent / f"messages_pre_bot_migration_{ts}.db"
    shutil.copy2(DB_PATH, backup)
    print(f"Backup creado: {backup}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for table, old_idx, new_idx in MIGRATIONS:
        # Verificar si ya fue migrada
        cur.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cur.fetchall()]

        if "bot_id" in cols:
            print(f"  {table}: ya migrada (bot_id existe), saltando.")
            continue

        if "empresa_id" not in cols:
            print(f"  {table}: sin columna empresa_id, saltando.")
            continue

        print(f"  {table}: renombrando empresa_id → bot_id...")
        cur.execute(f"ALTER TABLE {table} RENAME COLUMN empresa_id TO bot_id")

        print(f"  {table}: eliminando índice viejo {old_idx}...")
        cur.execute(f"DROP INDEX IF EXISTS {old_idx}")

        print(f"  {table}: creando índice nuevo {new_idx}...")
        cur.execute(f"CREATE INDEX IF NOT EXISTS {new_idx} ON {table}(bot_id)")

    conn.commit()
    conn.close()
    print("Migración completada.")


if __name__ == "__main__":
    main()
