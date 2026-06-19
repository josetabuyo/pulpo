#!/usr/bin/env python3
"""Refactor profundo: empresa → bot en todo el proyecto Pulpo."""

import os
import sys
from pathlib import Path

WDIR = Path(__file__).parent.parent

REPLACEMENTS = [
    # Funciones específicas (más largas primero para evitar solapamientos)
    ("get_empresa_id_from_token", "get_bot_id_from_token"),
    ("require_empresa_auth", "require_bot_auth"),
    ("_require_empresa_or_admin", "_require_bot_or_admin"),
    ("_require_empresa", "_require_bot"),
    ("set_empresa_paused", "set_bot_paused"),
    ("get_empresa_paused", "get_bot_paused"),
    ("empresa_has_node_type", "bot_has_node_type"),
    ("flow_exists_for_empresa", "flow_exists_for_bot"),
    ("empresa_clear_suggested_contacts", "bot_clear_suggested_contacts"),
    ("empresa_delete_one_suggestion", "bot_delete_one_suggestion"),
    ("empresa_add_telegram", "bot_add_telegram"),
    ("empresa_remove_telegram", "bot_remove_telegram"),
    ("empresa_put_config", "bot_put_config"),
    ("empresa_chat_send", "bot_chat_send"),
    ("empresa_chat_get", "bot_chat_get"),
    ("empresa_messages", "bot_messages"),
    ("empresa_nueva", "bot_new"),
    ("empresa_auth", "bot_auth"),
    ("empresa_get", "bot_get"),
    ("empresa_refresh", "bot_refresh"),
    ("empresa_logout", "bot_logout"),
    ("empresa_login", "bot_login"),
    ("empresa_me", "bot_me"),
    ("empresa_limiter", "bot_limiter"),
    ("empresa_paused", "bot_paused"),

    # Modelos Pydantic / clases
    ("NuevaEmpresaBody", "NewBotBody"),
    ("EmpresaConfigBody", "BotConfigBody"),
    ("EmpresaAuthBody", "BotAuthBody"),
    ("EmpresaSendBody", "BotSendBody"),
    ("EmpresaLoginBody", "BotLoginBody"),

    # Componentes React (PascalCase)
    ("NuevaEmpresaPage", "NewBotPage"),
    ("EmpresaConfigTab", "BotConfigTab"),
    ("EmpresaCard", "BotCard"),
    ("EmpresaPage", "BotPage"),

    # Imports Python (rutas de módulos)
    ("api.auth_empresa", "api.auth_bot"),
    ("auth_empresa_router", "auth_bot_router"),
    ("from .auth_empresa", "from .auth_bot"),
    ("api.empresa", "api.bot_portal"),
    ("from api import empresa", "from api import bot_portal"),
    ("empresa_router", "bot_portal_router"),

    # Imports frontend (rutas de archivos)
    ("components/empresa/", "components/bot/"),
    ("./empresa/", "./bot/"),
    ("../empresa/", "../bot/"),

    # Columna/variable más común
    ("empresa_id", "bot_id"),

    # Rutas API (strings en código)
    ('"/empresa/', '"/bot/'),
    ("'/empresa/", "'/bot/"),
    ('`/empresa/', '`/bot/'),
    ('"empresa/', '"bot/'),
    ("'empresa/", "'bot/"),

    # Claves de config JSON
    ('"empresas"', '"bots"'),
    ("'empresas'", "'bots'"),
    ('.get("empresas"', '.get("bots"'),
    (".get('empresas'", ".get('bots'"),

    # camelCase JavaScript
    ("empresaId", "botId"),

    # Generales (al final, más cortas — capturan lo que quedó)
    ("Empresa", "Bot"),
    ("empresa", "bot"),
]

INCLUDE_EXTENSIONS = {".py", ".jsx", ".js", ".ts", ".tsx", ".json", ".md", ".txt", ".sh"}
EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", ".pytest_cache", ".venv", "venv"}
EXCLUDE_FILES = {"phones.json", "refactor_empresa_to_bot.py"}


def should_process(path: Path) -> bool:
    if path.is_symlink():
        return False
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return False
    if path.name in EXCLUDE_FILES:
        return False
    return path.suffix in INCLUDE_EXTENSIONS


def process_file(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return False

    new_content = content
    for old, new in REPLACEMENTS:
        new_content = new_content.replace(old, new)

    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
        return True
    return False


def main():
    dry_run = "--dry-run" in sys.argv
    changed = []
    for root, dirs, files in os.walk(WDIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            fpath = Path(root) / fname
            if should_process(fpath):
                if dry_run:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    new = content
                    for old, new_val in REPLACEMENTS:
                        new = new.replace(old, new_val)
                    if new != content:
                        rel = fpath.relative_to(WDIR)
                        changed.append(str(rel))
                else:
                    if process_file(fpath):
                        rel = fpath.relative_to(WDIR)
                        changed.append(str(rel))

    if dry_run:
        print(f"[DRY RUN] {len(changed)} archivos cambiarían:")
    else:
        print(f"Modificados {len(changed)} archivos:")
    for f in sorted(changed):
        print(f"  {f}")


if __name__ == "__main__":
    main()
