from pathlib import Path
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

_DB_PATH = Path(__file__).parent.parent / "data" / "messages.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    """Activa foreign keys en SQLite para que ON DELETE CASCADE funcione."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS messages (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id  TEXT NOT NULL,
                connection_phone TEXT NOT NULL,
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
                connection_id TEXT NOT NULL,
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
            "CREATE INDEX IF NOT EXISTS idx_sessions_connection_id ON sessions(connection_id)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS contacts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id TEXT NOT NULL,
                name       TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contacts_connection_id ON contacts(connection_id)"
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

        # Migración: eliminar sistema legacy de tools (reemplazado por flows)
        for _old_table in ("tool_contacts_excluded", "tool_contacts_included", "tool_connections", "tools"):
            await conn.execute(text(f"DROP TABLE IF EXISTS {_old_table}"))

        # ─── Flows ───────────────────────────────────────────────────
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS flows (
                id            TEXT PRIMARY KEY,
                empresa_id    TEXT NOT NULL,
                name          TEXT NOT NULL,
                definition    TEXT NOT NULL DEFAULT '{}',
                connection_id TEXT DEFAULT NULL,
                contact_phone TEXT DEFAULT NULL,
                active        INTEGER NOT NULL DEFAULT 1,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_flows_empresa_id ON flows(empresa_id)"
        ))
        # Migración: agregar contact_filter si la tabla ya existía sin esa columna
        try:
            await conn.execute(text("ALTER TABLE flows ADD COLUMN contact_filter TEXT DEFAULT NULL"))
        except Exception:
            pass  # Ya existe

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS contact_suggestions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id TEXT NOT NULL,
                name       TEXT,
                phone      TEXT,
                source     TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(empresa_id, name, phone)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contact_suggestions_empresa ON contact_suggestions(empresa_id)"
        ))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS jobs (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id        TEXT NOT NULL,
                cliente_phone     TEXT NOT NULL,
                cliente_name      TEXT,
                canal             TEXT NOT NULL,
                oficio            TEXT NOT NULL,
                trabajador_id     TEXT,
                trabajador_nombre TEXT,
                status            TEXT NOT NULL DEFAULT 'pending',
                created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_jobs_empresa_id ON jobs(empresa_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"
        ))

async def create_job(
    empresa_id: str,
    cliente_phone: str,
    canal: str,
    oficio: str,
    trabajador_id: str | None = None,
    trabajador_nombre: str | None = None,
    cliente_name: str | None = None,
) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                INSERT INTO jobs (empresa_id, cliente_phone, cliente_name, canal, oficio, trabajador_id, trabajador_nombre)
                VALUES (:empresa_id, :cliente_phone, :cliente_name, :canal, :oficio, :trabajador_id, :trabajador_nombre)
            """),
            {
                "empresa_id": empresa_id,
                "cliente_phone": cliente_phone,
                "cliente_name": cliente_name,
                "canal": canal,
                "oficio": oficio,
                "trabajador_id": trabajador_id,
                "trabajador_nombre": trabajador_nombre,
            },
        )
        await session.commit()
        return result.lastrowid

async def log_message(connection_id: str, connection_phone: str, phone: str, name: str | None, body: str, outbound: bool = False) -> int:
    async with AsyncSessionLocal() as session:
        # Dedup: evitar loguear el mismo mensaje si ya existe en los últimos 10 minutos
        # (cubre el caso de reinicios del servidor que vacían el seen_pairs en memoria)
        existing = (await session.execute(
            text("""
                SELECT id FROM messages
                WHERE connection_id=:connection_id AND phone=:phone AND body=:body
                AND timestamp >= datetime('now', '-10 minutes')
                LIMIT 1
            """),
            {"connection_id": connection_id, "phone": phone, "body": body},
        )).fetchone()
        if existing:
            return existing[0]
        result = await session.execute(
            text("INSERT INTO messages (connection_id, connection_phone, phone, name, body, outbound) VALUES (:connection_id, :connection_phone, :phone, :name, :body, :outbound)"),
            {"connection_id": connection_id, "connection_phone": connection_phone, "phone": phone, "name": name, "body": body, "outbound": 1 if outbound else 0},
        )
        await session.commit()
        return result.lastrowid


_AUDIO_PLACEHOLDERS = ("[audio]", "[media]", "[audio — sin blob]", "[audio — error al transcribir]")


async def log_message_historic(
    connection_id: str, connection_phone: str, phone: str, name: str | None,
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
                WHERE connection_id=:connection_id AND phone=:phone AND body=:body
                AND strftime('%Y-%m-%d %H:%M', timestamp) = strftime('%Y-%m-%d %H:%M', :ts)
                LIMIT 1
            """),
            {"connection_id": connection_id, "phone": phone, "body": body, "ts": timestamp},
        )).fetchone()
        if existing:
            return False

        # Si es transcripción real, reemplazar el placeholder [audio]/[media] previo
        if replace_audio and body not in _AUDIO_PLACEHOLDERS:
            await session.execute(
                text("""
                    DELETE FROM messages
                    WHERE connection_id=:connection_id AND phone=:phone
                    AND body IN ('[audio]', '[media]')
                    AND strftime('%Y-%m-%d %H:%M', timestamp) = strftime('%Y-%m-%d %H:%M', :ts)
                """),
                {"connection_id": connection_id, "phone": phone, "ts": timestamp},
            )

        await session.execute(
            text("INSERT INTO messages (connection_id, connection_phone, phone, name, body, timestamp, outbound) "
                 "VALUES (:connection_id, :connection_phone, :phone, :name, :body, :timestamp, :outbound)"),
            {"connection_id": connection_id, "connection_phone": connection_phone, "phone": phone, "name": name,
             "body": body, "timestamp": timestamp, "outbound": outbound},
        )
        await session.commit()
        return True


async def log_outbound_message(connection_id: str, connection_phone: str, phone: str, body: str) -> int:
    """Registra un mensaje enviado por el bot (respuesta automática o manual)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("INSERT INTO messages (connection_id, connection_phone, phone, name, body, answered, outbound) "
                 "VALUES (:connection_id, :connection_phone, :phone, 'Bot', :body, 1, 1)"),
            {"connection_id": connection_id, "connection_phone": connection_phone, "phone": phone, "body": body},
        )
        await session.commit()
        return result.lastrowid


async def create_session(connection_id: str, refresh_token: str, expires_at: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("INSERT INTO sessions (connection_id, refresh_token, expires_at) VALUES (:connection_id, :token, :expires_at)"),
            {"connection_id": connection_id, "token": refresh_token, "expires_at": expires_at},
        )
        await session.commit()
        return result.lastrowid


async def get_session(refresh_token: str) -> dict | None:
    """Devuelve la sesión si existe, no está revocada y no expiró."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, connection_id, refresh_token, created_at, expires_at
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
    return {"id": row[0], "connection_id": row[1], "refresh_token": row[2],
            "created_at": row[3], "expires_at": row[4]}


async def revoke_session(refresh_token: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("UPDATE sessions SET revoked = 1 WHERE refresh_token = :token"),
            {"token": refresh_token},
        )
        await session.commit()
        return result.rowcount > 0


async def revoke_all_sessions(connection_id: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("UPDATE sessions SET revoked = 1 WHERE connection_id = :connection_id AND revoked = 0"),
            {"connection_id": connection_id},
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


async def create_contact(connection_id: str, name: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("INSERT INTO contacts (connection_id, name) VALUES (:connection_id, :name)"),
            {"connection_id": connection_id, "name": name},
        )
        await session.commit()
        return result.lastrowid


async def get_contacts(connection_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("SELECT id, connection_id, name, created_at FROM contacts WHERE connection_id = :connection_id ORDER BY id"),
            {"connection_id": connection_id},
        )).fetchall()
        if not rows:
            return []
        contact_ids = [r[0] for r in rows]
        channels_map = await _get_channels_for(session, contact_ids)
        return [
            {"id": r[0], "connection_id": r[1], "name": r[2], "created_at": str(r[3]),
             "channels": channels_map.get(r[0], [])}
            for r in rows
        ]


async def get_contact(contact_id: int) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("SELECT id, connection_id, name, created_at FROM contacts WHERE id = :id"),
            {"id": contact_id},
        )).fetchone()
        if not row:
            return None
        channels_map = await _get_channels_for(session, [row[0]])
        return {"id": row[0], "connection_id": row[1], "name": row[2], "created_at": str(row[3]),
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
        await session.execute(
            text("DELETE FROM contact_channels WHERE contact_id = :id"),
            {"id": contact_id},
        )
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
                text("SELECT id, connection_id, name, created_at FROM contacts WHERE name = :name"),
                {"name": value},
            )).fetchone()
            if not contact_row:
                return None
            contact_id = contact_row[0]
        else:
            contact_id = row[0]
            contact_row = (await session.execute(
                text("SELECT id, connection_id, name, created_at FROM contacts WHERE id = :id"),
                {"id": contact_id},
            )).fetchone()
            if not contact_row:
                return None

        channels_map = await _get_channels_for(session, [contact_id])
        return {"id": contact_row[0], "connection_id": contact_row[1], "name": contact_row[2],
                "created_at": str(contact_row[3]), "channels": channels_map.get(contact_id, [])}


# ─── Flows ───────────────────────────────────────────────────────

import json as _json
import uuid as _uuid


def _flow_row_to_dict(row, include_definition: bool = False) -> dict:
    # columns: id, empresa_id, name, definition, connection_id, contact_phone, active, created_at, updated_at, contact_filter
    raw_cf = row[9] if len(row) > 9 else None
    contact_filter = None
    if raw_cf:
        try:
            contact_filter = _json.loads(raw_cf)
        except Exception:
            pass
    d = {
        "id":             row[0],
        "empresa_id":     row[1],
        "name":           row[2],
        "connection_id":  row[4],
        "contact_phone":  row[5],
        "active":         bool(row[6]),
        "created_at":     str(row[7]),
        "updated_at":     str(row[8]),
        "contact_filter": contact_filter,
    }
    if include_definition:
        raw = row[3]
        if raw and raw.strip():
            try:
                d["definition"] = _json.loads(raw)
            except _json.JSONDecodeError:
                # Intentar arreglar escapes inválidos comunes
                # Reemplazar \! con ! (escape inválido en JSON)
                fixed = raw.replace('\\!', '!')
                try:
                    d["definition"] = _json.loads(fixed)
                except _json.JSONDecodeError:
                    # Si todavía falla, usar definición vacía
                    d["definition"] = {"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}
        else:
            d["definition"] = {"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}
    return d


async def create_flow(
    empresa_id: str,
    name: str,
    definition: dict | None = None,
    connection_id: str | None = None,
    contact_phone: str | None = None,
    contact_filter: dict | None = None,
) -> str:
    if not connection_id:
        raise ValueError(
            "connection_id es obligatorio al crear un flow. "
            "Un flow sin conexión no dispararía para nadie — asigná una conexión explícita."
        )
    flow_id = str(_uuid.uuid4())
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO flows (id, empresa_id, name, definition, connection_id, contact_phone, contact_filter)
                VALUES (:id, :empresa_id, :name, :definition, :connection_id, :contact_phone, :contact_filter)
            """),
            {
                "id": flow_id,
                "empresa_id": empresa_id,
                "name": name,
                "definition": _json.dumps(definition or {"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}),
                "connection_id": connection_id,
                "contact_phone": contact_phone,
                "contact_filter": _json.dumps(contact_filter) if contact_filter else None,
            },
        )
        await session.commit()
    return flow_id


async def get_flows(empresa_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("""
                SELECT id, empresa_id, name, definition, connection_id, contact_phone, active, created_at, updated_at, contact_filter
                FROM flows WHERE empresa_id = :e ORDER BY created_at
            """),
            {"e": empresa_id},
        )).fetchall()
    return [_flow_row_to_dict(r) for r in rows]


async def get_flow(flow_id: str) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("""
                SELECT id, empresa_id, name, definition, connection_id, contact_phone, active, created_at, updated_at, contact_filter
                FROM flows WHERE id = :id
            """),
            {"id": flow_id},
        )).fetchone()
    if not row:
        return None
    return _flow_row_to_dict(row, include_definition=True)


async def update_flow(flow_id: str, **kwargs) -> bool:
    allowed = {"name", "definition", "connection_id", "contact_phone", "active", "contact_filter"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    if "connection_id" in updates and not updates["connection_id"]:
        raise ValueError(
            "connection_id no puede quedar vacío. "
            "Un flow sin conexión no dispararía para nadie."
        )
    if "definition" in updates:
        updates["definition"] = _json.dumps(updates["definition"])
    if "contact_filter" in updates:
        updates["contact_filter"] = _json.dumps(updates["contact_filter"]) if updates["contact_filter"] else None
    if "active" in updates:
        updates["active"] = int(updates["active"])
    from datetime import datetime as _dt
    updates["updated_at"] = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k}=:{k}" for k in updates)
    updates["id"] = flow_id
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(f"UPDATE flows SET {set_clause} WHERE id=:id"), updates
        )
        await session.commit()
    return result.rowcount > 0


async def delete_flow(flow_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("DELETE FROM flows WHERE id=:id"), {"id": flow_id}
        )
        await session.commit()
    return result.rowcount > 0


async def flow_exists_for_empresa(empresa_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("SELECT id FROM flows WHERE empresa_id = :e LIMIT 1"),
            {"e": empresa_id},
        )).fetchone()
    return row is not None


async def get_last_message_body(connection_id: str, phone: str) -> str | None:
    """Retorna el body del mensaje más reciente para este contacto en este bot."""
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("SELECT body FROM messages WHERE connection_id=:connection_id AND phone=:phone "
                 "ORDER BY timestamp DESC LIMIT 1"),
            {"connection_id": connection_id, "phone": phone},
        )).fetchone()
        return row[0] if row else None


async def get_active_flows_for_bot(connection_id: str, contact_phone: str, empresa_id: str) -> list[dict]:
    """
    Flows activos para este (connection_id, contact_phone, empresa_id).

    Regla de seguridad: connection_id es OBLIGATORIO.
    Un flow sin connection_id asignado no dispara para nadie — NULL no es wildcard.
    contact_phone NULL sí es wildcard: el flow aplica a todos los contactos de esa conexión.

    Orden de especificidad: connection+contact > solo connection.
    """
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("""
                SELECT id, empresa_id, name, definition, connection_id, contact_phone, active, created_at, updated_at, contact_filter
                FROM flows
                WHERE empresa_id = :empresa_id
                  AND active = 1
                  AND connection_id = :connection_id
                  AND (contact_phone = :contact_phone OR contact_phone IS NULL)
                ORDER BY
                  CASE WHEN contact_phone IS NOT NULL THEN 1
                       ELSE 2 END
            """),
            {"empresa_id": empresa_id, "connection_id": connection_id, "contact_phone": contact_phone},
        )).fetchall()
    return [_flow_row_to_dict(r, include_definition=True) for r in rows]
