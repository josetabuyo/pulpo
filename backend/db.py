from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

_DB_PATH = Path(__file__).parent.parent / "data" / "messages.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id    TEXT NOT NULL,
                bot_phone TEXT NOT NULL,
                phone     TEXT NOT NULL,
                name      TEXT,
                body      TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                answered  INTEGER DEFAULT 0,
                outbound  INTEGER DEFAULT 0
            )
        """))
        # Migración: agregar outbound si la tabla ya existía sin esa columna
        try:
            await conn.execute(text("ALTER TABLE messages ADD COLUMN outbound INTEGER DEFAULT 0"))
        except Exception:
            pass  # Ya existe

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id        TEXT NOT NULL,
                refresh_token TEXT NOT NULL UNIQUE,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at    DATETIME NOT NULL,
                revoked       INTEGER NOT NULL DEFAULT 0
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(refresh_token)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sessions_bot_id ON sessions(bot_id)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS contacts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id     TEXT NOT NULL,
                name       TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contacts_bot_id ON contacts(bot_id)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS contact_channels (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                type       TEXT NOT NULL CHECK(type IN ('whatsapp', 'telegram')),
                value      TEXT NOT NULL,
                is_group   INTEGER NOT NULL DEFAULT 0,
                UNIQUE(type, value)
            )
        """))
        # Migración: agregar is_group si la tabla ya existía sin esa columna
        try:
            await conn.execute(text("ALTER TABLE contact_channels ADD COLUMN is_group INTEGER NOT NULL DEFAULT 0"))
        except Exception:
            pass  # Ya existe
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contact_channels_contact_id ON contact_channels(contact_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contact_channels_lookup ON contact_channels(type, value)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tools (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id           TEXT NOT NULL,
                nombre               TEXT NOT NULL,
                tipo                 TEXT NOT NULL CHECK(tipo IN ('fixed_message', 'summarizer')),
                config               TEXT NOT NULL,
                incluir_desconocidos INTEGER NOT NULL DEFAULT 0,
                exclusiva            INTEGER NOT NULL DEFAULT 0,
                activa               INTEGER NOT NULL DEFAULT 1,
                created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
                activated_at         DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Migración: agregar activated_at si no existe en tabla tools existente
        cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(tools)"))).fetchall()]
        if "activated_at" not in cols:
            await conn.execute(text("ALTER TABLE tools ADD COLUMN activated_at DATETIME"))
            await conn.execute(text("UPDATE tools SET activated_at = created_at WHERE activated_at IS NULL"))
        # Migración: si la tabla existe con el CHECK antiguo (sin 'summarizer'), recrearla
        schema_row = (await conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='tools'")
        )).fetchone()
        if schema_row and "'summarizer'" not in schema_row[0]:
            await conn.execute(text("ALTER TABLE tools RENAME TO _tools_bak"))
            await conn.execute(text("""
                CREATE TABLE tools (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    empresa_id           TEXT NOT NULL,
                    nombre               TEXT NOT NULL,
                    tipo                 TEXT NOT NULL CHECK(tipo IN ('fixed_message', 'summarizer')),
                    config               TEXT NOT NULL,
                    incluir_desconocidos INTEGER NOT NULL DEFAULT 0,
                    exclusiva            INTEGER NOT NULL DEFAULT 0,
                    activa               INTEGER NOT NULL DEFAULT 1,
                    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text(
                "INSERT INTO tools SELECT * FROM _tools_bak"
            ))
            await conn.execute(text("DROP TABLE _tools_bak"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_tools_empresa_id ON tools(empresa_id)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tool_connections (
                tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
                bot_id  TEXT NOT NULL,
                PRIMARY KEY (tool_id, bot_id)
            )
        """))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tool_contacts_included (
                tool_id    INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
                contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                PRIMARY KEY (tool_id, contact_id)
            )
        """))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tool_contacts_excluded (
                tool_id    INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
                contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                PRIMARY KEY (tool_id, contact_id)
            )
        """))

async def log_message(bot_id: str, bot_phone: str, phone: str, name: str | None, body: str) -> int:
    async with AsyncSessionLocal() as session:
        # Dedup: evitar loguear el mismo mensaje si ya existe en los últimos 10 minutos
        # (cubre el caso de reinicios del servidor que vacían el seen_pairs en memoria)
        existing = (await session.execute(
            text("""
                SELECT id FROM messages
                WHERE bot_id=:bot_id AND phone=:phone AND body=:body
                AND timestamp >= datetime('now', '-10 minutes')
                LIMIT 1
            """),
            {"bot_id": bot_id, "phone": phone, "body": body},
        )).fetchone()
        if existing:
            return existing[0]
        result = await session.execute(
            text("INSERT INTO messages (bot_id, bot_phone, phone, name, body) VALUES (:bot_id, :bot_phone, :phone, :name, :body)"),
            {"bot_id": bot_id, "bot_phone": bot_phone, "phone": phone, "name": name, "body": body},
        )
        await session.commit()
        return result.lastrowid


_AUDIO_PLACEHOLDERS = ("[audio]", "[media]", "[audio — sin blob]", "[audio — error al transcribir]")


async def log_message_historic(
    bot_id: str, bot_phone: str, phone: str, name: str | None,
    body: str, timestamp: str, outbound: int = 0,
    replace_audio: bool = False,
) -> bool:
    """
    Inserta un mensaje con timestamp específico (para sync histórico).
    Retorna True si fue insertado/actualizado, False si ya existía igual.

    Si replace_audio=True y el body es una transcripción real (no placeholder),
    elimina cualquier fila [audio]/[media] previa con el mismo minuto antes de insertar.
    """
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(
            text("""
                SELECT id FROM messages
                WHERE bot_id=:bot_id AND phone=:phone AND body=:body
                AND strftime('%Y-%m-%d %H:%M', timestamp) = strftime('%Y-%m-%d %H:%M', :ts)
                LIMIT 1
            """),
            {"bot_id": bot_id, "phone": phone, "body": body, "ts": timestamp},
        )).fetchone()
        if existing:
            return False

        # Si es transcripción real, reemplazar el placeholder [audio]/[media] previo
        if replace_audio and body not in _AUDIO_PLACEHOLDERS:
            await session.execute(
                text("""
                    DELETE FROM messages
                    WHERE bot_id=:bot_id AND phone=:phone
                    AND body IN ('[audio]', '[media]')
                    AND strftime('%Y-%m-%d %H:%M', timestamp) = strftime('%Y-%m-%d %H:%M', :ts)
                """),
                {"bot_id": bot_id, "phone": phone, "ts": timestamp},
            )

        await session.execute(
            text("INSERT INTO messages (bot_id, bot_phone, phone, name, body, timestamp, outbound) "
                 "VALUES (:bot_id, :bot_phone, :phone, :name, :body, :timestamp, :outbound)"),
            {"bot_id": bot_id, "bot_phone": bot_phone, "phone": phone, "name": name,
             "body": body, "timestamp": timestamp, "outbound": outbound},
        )
        await session.commit()
        return True


async def log_outbound_message(bot_id: str, bot_phone: str, phone: str, body: str) -> int:
    """Registra un mensaje enviado por el bot (respuesta automática o manual)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("INSERT INTO messages (bot_id, bot_phone, phone, name, body, answered, outbound) "
                 "VALUES (:bot_id, :bot_phone, :phone, 'Bot', :body, 1, 1)"),
            {"bot_id": bot_id, "bot_phone": bot_phone, "phone": phone, "body": body},
        )
        await session.commit()
        return result.lastrowid


async def create_session(bot_id: str, refresh_token: str, expires_at: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("INSERT INTO sessions (bot_id, refresh_token, expires_at) VALUES (:bot_id, :token, :expires_at)"),
            {"bot_id": bot_id, "token": refresh_token, "expires_at": expires_at},
        )
        await session.commit()
        return result.lastrowid


async def get_session(refresh_token: str) -> dict | None:
    """Devuelve la sesión si existe, no está revocada y no expiró."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, bot_id, refresh_token, created_at, expires_at
                FROM sessions
                WHERE refresh_token = :token
                  AND revoked = 0
                  AND expires_at > CURRENT_TIMESTAMP
            """),
            {"token": refresh_token},
        )
        row = result.fetchone()
    if not row:
        return None
    return {"id": row[0], "bot_id": row[1], "refresh_token": row[2],
            "created_at": row[3], "expires_at": row[4]}


async def revoke_session(refresh_token: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("UPDATE sessions SET revoked = 1 WHERE refresh_token = :token"),
            {"token": refresh_token},
        )
        await session.commit()
        return result.rowcount > 0


async def revoke_all_sessions(bot_id: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("UPDATE sessions SET revoked = 1 WHERE bot_id = :bot_id AND revoked = 0"),
            {"bot_id": bot_id},
        )
        await session.commit()
        return result.rowcount


async def mark_answered(msg_id: int):
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE messages SET answered = 1 WHERE id = :id"),
            {"id": msg_id},
        )
        await session.commit()


# ─── Contactos ───────────────────────────────────────────────────

async def _get_channels_for(conn, contact_ids: list[int]) -> dict[int, list]:
    if not contact_ids:
        return {}
    placeholders = ",".join(f":id{i}" for i in range(len(contact_ids)))
    params = {f"id{i}": cid for i, cid in enumerate(contact_ids)}
    rows = (await conn.execute(
        text(f"SELECT id, contact_id, type, value, is_group FROM contact_channels WHERE contact_id IN ({placeholders})"),
        params,
    )).fetchall()
    result: dict[int, list] = {cid: [] for cid in contact_ids}
    for row in rows:
        result[row[1]].append({"id": row[0], "type": row[2], "value": row[3], "is_group": bool(row[4])})
    return result


async def create_contact(bot_id: str, name: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("INSERT INTO contacts (bot_id, name) VALUES (:bot_id, :name)"),
            {"bot_id": bot_id, "name": name},
        )
        await session.commit()
        return result.lastrowid


async def get_contacts(bot_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("SELECT id, bot_id, name, created_at FROM contacts WHERE bot_id = :bot_id ORDER BY id"),
            {"bot_id": bot_id},
        )).fetchall()
        if not rows:
            return []
        contact_ids = [r[0] for r in rows]
        channels_map = await _get_channels_for(session, contact_ids)
        return [
            {"id": r[0], "bot_id": r[1], "name": r[2], "created_at": str(r[3]),
             "channels": channels_map.get(r[0], [])}
            for r in rows
        ]


async def get_contact(contact_id: int) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("SELECT id, bot_id, name, created_at FROM contacts WHERE id = :id"),
            {"id": contact_id},
        )).fetchone()
        if not row:
            return None
        channels_map = await _get_channels_for(session, [row[0]])
        return {"id": row[0], "bot_id": row[1], "name": row[2], "created_at": str(row[3]),
                "channels": channels_map.get(row[0], [])}


async def update_contact(contact_id: int, name: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("UPDATE contacts SET name = :name WHERE id = :id"),
            {"id": contact_id, "name": name},
        )
        await session.commit()
        return result.rowcount > 0


async def delete_contact(contact_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("DELETE FROM contacts WHERE id = :id"),
            {"id": contact_id},
        )
        await session.commit()
        return result.rowcount > 0


async def add_channel(contact_id: int, type: str, value: str, is_group: bool = False) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("INSERT INTO contact_channels (contact_id, type, value, is_group) VALUES (:contact_id, :type, :value, :is_group)"),
            {"contact_id": contact_id, "type": type, "value": value, "is_group": int(is_group)},
        )
        await session.commit()
        return result.lastrowid


async def delete_channel(channel_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("DELETE FROM contact_channels WHERE id = :id"),
            {"id": channel_id},
        )
        await session.commit()
        return result.rowcount > 0


async def find_contact_by_channel(type: str, value: str) -> dict | None:
    async with AsyncSessionLocal() as session:
        # Primero: buscar por valor exacto del canal (número de teléfono)
        row = (await session.execute(
            text("SELECT contact_id FROM contact_channels WHERE type = :type AND value = :value"),
            {"type": type, "value": value},
        )).fetchone()

        if not row:
            # Fallback: WA a veces solo provee el nombre, no el número.
            # Buscar en contacts por nombre exacto o aproximado.
            contact_row = (await session.execute(
                text("SELECT id, bot_id, name, created_at FROM contacts WHERE name = :name"),
                {"name": value},
            )).fetchone()
            if not contact_row:
                return None
            contact_id = contact_row[0]
        else:
            contact_id = row[0]
            contact_row = (await session.execute(
                text("SELECT id, bot_id, name, created_at FROM contacts WHERE id = :id"),
                {"id": contact_id},
            )).fetchone()
            if not contact_row:
                return None

        channels_map = await _get_channels_for(session, [contact_id])
        return {"id": contact_row[0], "bot_id": contact_row[1], "name": contact_row[2],
                "created_at": str(contact_row[3]), "channels": channels_map.get(contact_id, [])}


# ─── Tools ───────────────────────────────────────────────────────

import json as _json


async def _get_tool_details(conn, tool_ids: list[int]) -> dict:
    """Retorna {tool_id: {connections, contactos_incluidos, contactos_excluidos}}."""
    if not tool_ids:
        return {}
    ph = ",".join(f":t{i}" for i in range(len(tool_ids)))
    params = {f"t{i}": tid for i, tid in enumerate(tool_ids)}

    conns = (await conn.execute(
        text(f"SELECT tool_id, bot_id FROM tool_connections WHERE tool_id IN ({ph})"), params
    )).fetchall()

    inc = (await conn.execute(
        text(f"""SELECT ti.tool_id, c.id, c.name FROM tool_contacts_included ti
                 JOIN contacts c ON c.id = ti.contact_id WHERE ti.tool_id IN ({ph})"""), params
    )).fetchall()

    exc = (await conn.execute(
        text(f"""SELECT te.tool_id, c.id, c.name FROM tool_contacts_excluded te
                 JOIN contacts c ON c.id = te.contact_id WHERE te.tool_id IN ({ph})"""), params
    )).fetchall()

    result = {tid: {"connections": [], "contactos_incluidos": [], "contactos_excluidos": []} for tid in tool_ids}
    for r in conns:
        result[r[0]]["connections"].append(r[1])
    for r in inc:
        result[r[0]]["contactos_incluidos"].append({"id": r[1], "name": r[2]})
    for r in exc:
        result[r[0]]["contactos_excluidos"].append({"id": r[1], "name": r[2]})
    return result


def _tool_row_to_dict(row, details: dict) -> dict:
    tid = row[0]
    d = details.get(tid, {"connections": [], "contactos_incluidos": [], "contactos_excluidos": []})
    return {
        "id": tid,
        "empresa_id": row[1],
        "nombre": row[2],
        "tipo": row[3],
        "config": _json.loads(row[4]),
        "incluir_desconocidos": bool(row[5]),
        "exclusiva": bool(row[6]),
        "activa": bool(row[7]),
        "created_at": str(row[8]),
        "activated_at": str(row[9]) if len(row) > 9 and row[9] else str(row[8]),
        **d,
    }


async def create_tool(empresa_id: str, nombre: str, tipo: str, config: dict,
                      incluir_desconocidos: bool, exclusiva: bool) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""INSERT INTO tools (empresa_id, nombre, tipo, config, incluir_desconocidos, exclusiva)
                    VALUES (:empresa_id, :nombre, :tipo, :config, :inc, :exc)"""),
            {"empresa_id": empresa_id, "nombre": nombre, "tipo": tipo,
             "config": _json.dumps(config), "inc": int(incluir_desconocidos), "exc": int(exclusiva)},
        )
        await session.commit()
        return result.lastrowid


async def get_tools(empresa_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("SELECT id,empresa_id,nombre,tipo,config,incluir_desconocidos,exclusiva,activa,created_at,activated_at "
                 "FROM tools WHERE empresa_id=:e ORDER BY id"),
            {"e": empresa_id},
        )).fetchall()
        if not rows:
            return []
        details = await _get_tool_details(session, [r[0] for r in rows])
        return [_tool_row_to_dict(r, details) for r in rows]


async def get_tool(tool_id: int) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("SELECT id,empresa_id,nombre,tipo,config,incluir_desconocidos,exclusiva,activa,created_at,activated_at "
                 "FROM tools WHERE id=:id"),
            {"id": tool_id},
        )).fetchone()
        if not row:
            return None
        details = await _get_tool_details(session, [tool_id])
        return _tool_row_to_dict(row, details)


async def update_tool(tool_id: int, **kwargs) -> bool:
    allowed = {"nombre", "tipo", "config", "incluir_desconocidos", "exclusiva", "activa"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    if "config" in updates:
        updates["config"] = _json.dumps(updates["config"])
    for k in ("incluir_desconocidos", "exclusiva", "activa"):
        if k in updates:
            updates[k] = int(updates[k])
    # Actualizar activated_at cuando la tool se activa o se modifica su scope
    _triggers_activation = {"activa", "incluir_desconocidos", "exclusiva"}
    if _triggers_activation & set(updates.keys()):
        from datetime import datetime as _dt
        updates["activated_at"] = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k}=:{k}" for k in updates)
    updates["id"] = tool_id
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(f"UPDATE tools SET {set_clause} WHERE id=:id"), updates
        )
        await session.commit()
        return result.rowcount > 0


async def get_last_message_body(bot_id: str, phone: str) -> str | None:
    """Retorna el body del mensaje más reciente guardado para este contacto en este bot."""
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("SELECT body FROM messages WHERE bot_id=:bot_id AND phone=:phone "
                 "ORDER BY timestamp DESC LIMIT 1"),
            {"bot_id": bot_id, "phone": phone},
        )).fetchone()
        return row[0] if row else None


async def delete_tool(tool_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("DELETE FROM tools WHERE id=:id"), {"id": tool_id})
        await session.commit()
        return result.rowcount > 0


async def set_tool_connections(tool_id: int, bot_ids: list[str]) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM tool_connections WHERE tool_id=:tid"), {"tid": tool_id})
        for bid in bot_ids:
            await session.execute(
                text("INSERT INTO tool_connections (tool_id, bot_id) VALUES (:tid, :bid)"),
                {"tid": tool_id, "bid": bid},
            )
        await session.commit()


async def set_tool_contacts_included(tool_id: int, contact_ids: list[int]) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM tool_contacts_included WHERE tool_id=:tid"), {"tid": tool_id})
        for cid in contact_ids:
            await session.execute(
                text("INSERT INTO tool_contacts_included (tool_id, contact_id) VALUES (:tid, :cid)"),
                {"tid": tool_id, "cid": cid},
            )
        await session.commit()


async def set_tool_contacts_excluded(tool_id: int, contact_ids: list[int]) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM tool_contacts_excluded WHERE tool_id=:tid"), {"tid": tool_id})
        for cid in contact_ids:
            await session.execute(
                text("INSERT INTO tool_contacts_excluded (tool_id, contact_id) VALUES (:tid, :cid)"),
                {"tid": tool_id, "cid": cid},
            )
        await session.commit()


async def get_active_tools_for_bot(bot_id: str, empresa_id: str) -> list[dict]:
    """Herramientas activas que aplican a este bot (por conexión explícita o vacía=todas)."""
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("""
                SELECT DISTINCT t.id,t.empresa_id,t.nombre,t.tipo,t.config,
                       t.incluir_desconocidos,t.exclusiva,t.activa,t.created_at,t.activated_at
                FROM tools t
                LEFT JOIN tool_connections tc ON tc.tool_id = t.id
                WHERE t.empresa_id = :empresa_id
                  AND t.activa = 1
                  AND (tc.bot_id = :bot_id OR tc.bot_id IS NULL)
                ORDER BY t.id
            """),
            {"empresa_id": empresa_id, "bot_id": bot_id},
        )).fetchall()
        if not rows:
            return []
        details = await _get_tool_details(session, [r[0] for r in rows])
        return [_tool_row_to_dict(r, details) for r in rows]
