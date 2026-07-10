import logging
from pathlib import Path
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "messages.db"
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
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id     TEXT NOT NULL,
                name       TEXT NOT NULL,
                notes      TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Migraciones sobre contacts (antes de crear índices)
        try:
            await conn.execute(text("ALTER TABLE contacts ADD COLUMN notes TEXT"))
        except Exception:
            pass  # Ya existe
        try:
            await conn.execute(text("ALTER TABLE contacts RENAME COLUMN connection_id TO bot_id"))
        except Exception:
            pass  # Ya renombrada o columna nueva
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

        # Migración: eliminar sistema legacy de tools (reemplazado por flows)
        for _old_table in ("tool_contacts_excluded", "tool_contacts_included", "tool_connections", "tools"):
            await conn.execute(text(f"DROP TABLE IF EXISTS {_old_table}"))

        # ─── Flows ───────────────────────────────────────────────────
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS flows (
                id            TEXT PRIMARY KEY,
                bot_id    TEXT NOT NULL,
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
            "CREATE INDEX IF NOT EXISTS idx_flows_bot_id ON flows(bot_id)"
        ))
        # Migración: agregar contact_filter si la tabla ya existía sin esa columna
        try:
            await conn.execute(text("ALTER TABLE flows ADD COLUMN contact_filter TEXT DEFAULT NULL"))
        except Exception:
            pass  # Ya existe

        # ─── Flow Versions — historial de guardados explícitos ──────
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS flow_versions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                flow_id    TEXT NOT NULL REFERENCES flows(id) ON DELETE CASCADE,
                name       TEXT NOT NULL,
                definition TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_flow_versions_flow_id ON flow_versions(flow_id, created_at)"
        ))

        # Eliminar tabla legacy contact_suggestions (scraper WA removido)
        await conn.execute(text("DROP TABLE IF EXISTS contact_suggestions"))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS jobs (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id        TEXT NOT NULL,
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
            "CREATE INDEX IF NOT EXISTS idx_jobs_bot_id ON jobs(bot_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"
        ))

        # ─── Google Connections ───────────────────────────────────────
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS google_connections (
                id               TEXT PRIMARY KEY,
                bot_id       TEXT,
                credentials_json TEXT NOT NULL,
                email            TEXT NOT NULL,
                label            TEXT NOT NULL,
                created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_google_connections_bot ON google_connections(bot_id)"
        ))

        # ─── Wavi: dedup persistente del poller ──────────────────────
        # Sobrevive reinicios: evita re-responder el último mensaje de cada
        # chat cuando el cache en memoria del poller se pierde.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS wavi_seen (
                session    TEXT NOT NULL,
                contact    TEXT NOT NULL,
                msg_hash   TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session, contact, msg_hash)
            )
        """))

        # ─── Flow Runs — journal (ADR-006) ───────────────────────────
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS flow_runs (
                run_id        TEXT PRIMARY KEY,
                flow_id       TEXT NOT NULL,
                bot_id        TEXT NOT NULL,
                connection_id TEXT,
                started_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                ended_at      DATETIME,
                status        TEXT DEFAULT 'running',
                trigger_data  TEXT
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_flow_runs_bot_id ON flow_runs(bot_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_flow_runs_flow_id ON flow_runs(flow_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_flow_runs_started ON flow_runs(started_at)"
        ))
        # Migraciones wait_user: columnas para dispatcher de reanudación
        for _col, _default in [
            ("contact_phone", "NULL"),
            ("resume_node_id", "NULL"),
            ("slots_json", "NULL"),
        ]:
            try:
                await conn.execute(text(f"ALTER TABLE flow_runs ADD COLUMN {_col} TEXT DEFAULT {_default}"))
            except Exception:
                pass  # Ya existe
        # Migración simulación in-band (management/HANDOFF_SIMULACION_V2.md)
        try:
            await conn.execute(text("ALTER TABLE flow_runs ADD COLUMN is_sim BOOLEAN DEFAULT 0"))
        except Exception:
            pass  # Ya existe
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_flow_runs_waiting ON flow_runs(bot_id, contact_phone, status)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS flow_run_steps (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id        TEXT NOT NULL REFERENCES flow_runs(run_id),
                node_id       TEXT NOT NULL,
                node_type     TEXT NOT NULL,
                started_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                ended_at      DATETIME,
                input_state   TEXT,
                output_state  TEXT,
                branch_taken  TEXT,
                status        TEXT DEFAULT 'ok'
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_flow_run_steps_run_id ON flow_run_steps(run_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS metrics (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id         TEXT NOT NULL,
                contact_phone  TEXT,
                contact_name   TEXT,
                canal          TEXT,
                metric_name    TEXT NOT NULL,
                value          TEXT,
                metadata       TEXT,
                created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_metrics_bot_id ON metrics(bot_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_metrics_metric_name ON metrics(metric_name)"
        ))

        # ─── Conversación abierta más allá del wait_user ─────────────
        # Estado explícito (no derivado de tiempo transcurrido): un mensaje nuevo
        # sin wait_user pendiente encuentra acá si hay charla en curso para
        # continuar. Se cierra por end_conversation (explícito) o por un cron
        # externo que llama prune_open_conversations() (abandono).
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS open_conversations (
                bot_id            TEXT NOT NULL,
                contact_phone     TEXT NOT NULL,
                connection_id     TEXT,
                flow_id           TEXT,
                conversation_json TEXT NOT NULL,
                updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (bot_id, contact_phone)
            )
        """))

async def create_job(
    bot_id: str,
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
                INSERT INTO jobs (bot_id, cliente_phone, cliente_name, canal, oficio, trabajador_id, trabajador_nombre)
                VALUES (:bot_id, :cliente_phone, :cliente_name, :canal, :oficio, :trabajador_id, :trabajador_nombre)
            """),
            {
                "bot_id": bot_id,
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


# ─── Wavi: dedup persistente del poller ──────────────────────────────────────
# El poller identifica mensajes por (session, contact, hash del texto).

def wavi_msg_hash(text_value: str) -> str:
    import hashlib
    return hashlib.sha256(text_value.encode("utf-8")).hexdigest()[:16]


async def wavi_seen_has(session_name: str, contact: str, msg_hash: str) -> bool:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("SELECT 1 FROM wavi_seen WHERE session=:s AND contact=:c AND msg_hash=:h LIMIT 1"),
            {"s": session_name, "c": contact, "h": msg_hash},
        )).fetchone()
    return row is not None


async def wavi_seen_add(session_name: str, contact: str, msg_hash: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("INSERT OR IGNORE INTO wavi_seen (session, contact, msg_hash) VALUES (:s, :c, :h)"),
            {"s": session_name, "c": contact, "h": msg_hash},
        )
        await session.commit()


async def wavi_seen_prune(days: int = 14) -> int:
    """Borra entradas más viejas que `days`. El dedup solo necesita cubrir
    la ventana en la que un mensaje puede reaparecer en el sidebar."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("DELETE FROM wavi_seen WHERE created_at < datetime('now', :cutoff)"),
            {"cutoff": f"-{int(days)} days"},
        )
        await session.commit()
        return result.rowcount or 0


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


async def create_contact(bot_id: str, name: str, notes: str | None = None) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("INSERT INTO contacts (bot_id, name, notes) VALUES (:bot_id, :name, :notes)"),
            {"bot_id": bot_id, "name": name, "notes": notes},
        )
        await session.commit()
        return result.lastrowid


async def get_contacts(bot_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("SELECT id, bot_id, name, notes, created_at FROM contacts WHERE bot_id = :bot_id ORDER BY id"),
            {"bot_id": bot_id},
        )).fetchall()
        if not rows:
            return []
        contact_ids = [r[0] for r in rows]
        channels_map = await _get_channels_for(session, contact_ids)
        return [
            {"id": r[0], "bot_id": r[1], "name": r[2], "notes": r[3], "created_at": str(r[4]),
             "channels": channels_map.get(r[0], [])}
            for r in rows
        ]


async def get_contact(contact_id: int) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("SELECT id, bot_id, name, notes, created_at FROM contacts WHERE id = :id"),
            {"id": contact_id},
        )).fetchone()
        if not row:
            return None
        channels_map = await _get_channels_for(session, [row[0]])
        return {"id": row[0], "bot_id": row[1], "name": row[2], "notes": row[3], "created_at": str(row[4]),
                "channels": channels_map.get(row[0], [])}


async def update_contact(contact_id: int, name: str, notes: str | None = None) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("UPDATE contacts SET name = :name, notes = :notes WHERE id = :id"),
            {"id": contact_id, "name": name, "notes": notes},
        )
        await session.commit()
        return result.rowcount > 0


async def delete_contact_messages(bot_id: str, contact_name: str) -> int:
    """Borra todos los mensajes de un contacto en una bot. Retorna filas eliminadas.
    contact_name es el valor almacenado en la columna phone de la tabla messages."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("DELETE FROM messages WHERE connection_id = :bot_id AND phone = :name"),
            {"bot_id": bot_id, "name": contact_name},
        )
        await session.commit()
        return result.rowcount


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


# ─── Flows ───────────────────────────────────────────────────────

import json as _json
import uuid as _uuid


def _flow_row_to_dict(row, include_definition: bool = False) -> dict:
    # columns: id, bot_id, name, definition, connection_id, contact_phone, active, created_at, updated_at, contact_filter
    raw_cf = row[9] if len(row) > 9 else None
    contact_filter = None
    if raw_cf:
        try:
            contact_filter = _json.loads(raw_cf)
        except ValueError as e:
            logger.warning("contact_filter corrupto en flow %s — ignorado: %s", row[0], e)
    d = {
        "id":             row[0],
        "bot_id":     row[1],
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
    bot_id: str,
    name: str,
    definition: dict | None = None,
    connection_id: str | None = None,
    contact_phone: str | None = None,
    contact_filter: dict | None = None,
) -> str:
    flow_id = str(_uuid.uuid4())
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO flows (id, bot_id, name, definition, connection_id, contact_phone, contact_filter)
                VALUES (:id, :bot_id, :name, :definition, :connection_id, :contact_phone, :contact_filter)
            """),
            {
                "id": flow_id,
                "bot_id": bot_id,
                "name": name,
                "definition": _json.dumps(definition or {"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}),
                "connection_id": connection_id,
                "contact_phone": contact_phone,
                "contact_filter": _json.dumps(contact_filter) if contact_filter else None,
            },
        )
        await session.commit()
    return flow_id


async def get_all_flow_ids() -> list[str]:
    """Todos los flow ids, sin filtrar por bot — solo para migraciones one-shot."""
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text("SELECT id FROM flows"))).fetchall()
    return [r[0] for r in rows]


async def get_flows(bot_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("""
                SELECT id, bot_id, name, definition, connection_id, contact_phone, active, created_at, updated_at, contact_filter
                FROM flows WHERE bot_id = :e ORDER BY created_at
            """),
            {"e": bot_id},
        )).fetchall()
    return [_flow_row_to_dict(r) for r in rows]


async def bot_has_node_type(bot_id: str, node_type: str) -> bool:
    """Devuelve True si algún flow de la bot contiene un nodo del tipo dado."""
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text(
                "SELECT 1 FROM flows "
                "WHERE bot_id = :e AND definition LIKE :pattern LIMIT 1"
            ),
            {"e": bot_id, "pattern": f'%"type": "{node_type}"%'},
        )).fetchone()
    return row is not None


async def get_flow(flow_id: str) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("""
                SELECT id, bot_id, name, definition, connection_id, contact_phone, active, created_at, updated_at, contact_filter
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


_FLOW_VERSIONS_LIMIT = 50


async def create_flow_version(flow_id: str, name: str, definition: dict) -> None:
    """Guarda un snapshot del flow y poda al límite de últimas 50 versiones."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO flow_versions (flow_id, name, definition)
                VALUES (:flow_id, :name, :definition)
            """),
            {"flow_id": flow_id, "name": name, "definition": _json.dumps(definition)},
        )
        await session.execute(
            text(f"""
                DELETE FROM flow_versions WHERE flow_id=:flow_id AND id NOT IN (
                    SELECT id FROM flow_versions WHERE flow_id=:flow_id
                    ORDER BY created_at DESC LIMIT {_FLOW_VERSIONS_LIMIT}
                )
            """),
            {"flow_id": flow_id},
        )
        await session.commit()


async def get_flow_versions(flow_id: str, limit: int = _FLOW_VERSIONS_LIMIT) -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("""
                SELECT id, flow_id, name, created_at FROM flow_versions
                WHERE flow_id = :flow_id ORDER BY created_at DESC LIMIT :limit
            """),
            {"flow_id": flow_id, "limit": limit},
        )).fetchall()
    return [
        {"id": r[0], "flow_id": r[1], "name": r[2], "created_at": str(r[3])}
        for r in rows
    ]


async def get_flow_version(version_id: int) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("""
                SELECT id, flow_id, name, definition, created_at FROM flow_versions
                WHERE id = :id
            """),
            {"id": version_id},
        )).fetchone()
    if not row:
        return None
    try:
        definition = _json.loads(row[3])
    except _json.JSONDecodeError:
        definition = {"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}
    return {
        "id": row[0],
        "flow_id": row[1],
        "name": row[2],
        "definition": definition,
        "created_at": str(row[4]),
    }


async def flow_exists_for_bot(bot_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("SELECT id FROM flows WHERE bot_id = :e LIMIT 1"),
            {"e": bot_id},
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


async def get_active_flows_for_bot(connection_id: str, contact_phone: str, bot_id: str) -> list[dict]:
    """
    Flows activos para este (connection_id, contact_phone, bot_id).

    Regla de seguridad: connection_id es OBLIGATORIO.
    Un flow sin connection_id asignado no dispara para nadie — NULL no es wildcard.
    contact_phone NULL sí es wildcard: el flow aplica a todos los contactos de esa conexión.

    Orden de especificidad: connection+contact > solo connection.
    """
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("""
                SELECT id, bot_id, name, definition, connection_id, contact_phone, active, created_at, updated_at, contact_filter
                FROM flows
                WHERE bot_id = :bot_id
                  AND active = 1
                  AND connection_id = :connection_id
                  AND (contact_phone = :contact_phone OR contact_phone IS NULL)
                ORDER BY
                  CASE WHEN contact_phone IS NOT NULL THEN 1
                       ELSE 2 END
            """),
            {"bot_id": bot_id, "connection_id": connection_id, "contact_phone": contact_phone},
        )).fetchall()
    return [_flow_row_to_dict(r, include_definition=True) for r in rows]


# ─── Google Connections ───────────────────────────────────────────────────────

def _google_conn_row(row) -> dict:
    return {
        "id":         row[0],
        "bot_id": row[1],
        "email":      row[3],
        "label":      row[4],
        "created_at": str(row[5]),
    }


async def get_google_connections(bot_id: str | None = None) -> list[dict]:
    """
    Retorna conexiones Google disponibles para una bot:
    las propias + la pulpo-default (bot_id IS NULL).
    Si bot_id es None devuelve todas (uso admin).
    """
    async with AsyncSessionLocal() as session:
        if bot_id is None:
            rows = (await session.execute(
                text("SELECT id, bot_id, credentials_json, email, label, created_at FROM google_connections ORDER BY created_at")
            )).fetchall()
        else:
            rows = (await session.execute(
                text("""
                    SELECT id, bot_id, credentials_json, email, label, created_at
                    FROM google_connections
                    WHERE bot_id = :e OR bot_id IS NULL
                    ORDER BY bot_id IS NOT NULL DESC, created_at
                """),
                {"e": bot_id},
            )).fetchall()
    return [_google_conn_row(r) for r in rows]


async def get_google_connection_credentials(conn_id: str) -> str | None:
    """Retorna el credentials_json de una conexión Google por su id."""
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("SELECT credentials_json FROM google_connections WHERE id = :id"),
            {"id": conn_id},
        )).fetchone()
    return row[0] if row else None


async def create_google_connection(
    id: str,
    bot_id: str | None,
    credentials_json: str,
    email: str,
    label: str,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO google_connections (id, bot_id, credentials_json, email, label)
                VALUES (:id, :bot_id, :credentials_json, :email, :label)
            """),
            {"id": id, "bot_id": bot_id, "credentials_json": credentials_json,
             "email": email, "label": label},
        )
        await session.commit()


async def google_connection_exists(conn_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("SELECT 1 FROM google_connections WHERE id = :id"),
            {"id": conn_id},
        )).fetchone()
    return row is not None


async def delete_google_connection(conn_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("DELETE FROM google_connections WHERE id = :id"),
            {"id": conn_id},
        )
        await session.commit()
    return result.rowcount > 0


# ─── Flow Runs — journal (ADR-006) ───────────────────────────────────────────

async def start_flow_run(
    run_id: str,
    flow_id: str,
    bot_id: str,
    connection_id: str | None,
    trigger_data: str | None,
    is_sim: bool = False,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO flow_runs (run_id, flow_id, bot_id, connection_id, trigger_data, is_sim)
                VALUES (:run_id, :flow_id, :bot_id, :connection_id, :trigger_data, :is_sim)
            """),
            {"run_id": run_id, "flow_id": flow_id, "bot_id": bot_id,
             "connection_id": connection_id, "trigger_data": trigger_data,
             "is_sim": 1 if is_sim else 0},
        )
        await session.commit()


async def end_flow_run(run_id: str, status: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE flow_runs SET status=:status, ended_at=CURRENT_TIMESTAMP WHERE run_id=:run_id"),
            {"run_id": run_id, "status": status},
        )
        await session.commit()


async def set_wait_user_info(
    run_id: str,
    contact_phone: str,
    resume_node_id: str,
    slots_json: str,
) -> None:
    """Persiste el punto de reanudación y el estado cuando wait_user bloquea."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                UPDATE flow_runs
                SET contact_phone=:cp, resume_node_id=:rn, slots_json=:sj
                WHERE run_id=:run_id
            """),
            {"run_id": run_id, "cp": contact_phone, "rn": resume_node_id, "sj": slots_json},
        )
        await session.commit()


async def get_waiting_gate_run(bot_id: str, contact_phone: str) -> dict | None:
    """Retorna el run en waiting_gate más reciente para este (bot, contacto), si existe."""
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("""
                SELECT run_id, flow_id, resume_node_id, slots_json, started_at
                FROM flow_runs
                WHERE bot_id=:bot_id
                  AND contact_phone=:contact_phone
                  AND status='waiting_gate'
                ORDER BY started_at DESC
                LIMIT 1
            """),
            {"bot_id": bot_id, "contact_phone": contact_phone},
        )).fetchone()
    if not row:
        return None
    return {
        "run_id":         row[0],
        "flow_id":        row[1],
        "resume_node_id": row[2],
        "slots_json":     row[3],
        "started_at":     str(row[4]),
    }


async def expire_old_conversations(max_age_hours: int = 24) -> list[dict]:
    """Marca como 'expired' los runs en waiting_gate más viejos que max_age_hours.
    Retorna lista de {bot_id, contact_phone} de los runs expirados."""
    async with AsyncSessionLocal() as session:
        # Primero obtener los afectados para poder mandar despedida
        rows = (await session.execute(
            text("""
                SELECT bot_id, contact_phone
                FROM flow_runs
                WHERE status = 'waiting_gate'
                  AND contact_phone IS NOT NULL
                  AND started_at < datetime('now', :cutoff)
            """),
            {"cutoff": f"-{int(max_age_hours)} hours"},
        )).fetchall()
        expired = [{"bot_id": r[0], "contact_phone": r[1]} for r in rows]

        await session.execute(
            text("""
                UPDATE flow_runs
                SET status = 'expired', ended_at = CURRENT_TIMESTAMP
                WHERE status = 'waiting_gate'
                  AND started_at < datetime('now', :cutoff)
            """),
            {"cutoff": f"-{int(max_age_hours)} hours"},
        )
        await session.commit()
        return expired


async def close_waiting_conversations(bot_id: str, contact_phone: str) -> int:
    """Cierra todos los runs waiting_gate de este (bot, contacto). Retorna cantidad cerrada."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                UPDATE flow_runs
                SET status = 'completed', ended_at = CURRENT_TIMESTAMP
                WHERE bot_id = :bot_id
                  AND contact_phone = :contact_phone
                  AND status = 'waiting_gate'
            """),
            {"bot_id": bot_id, "contact_phone": contact_phone},
        )
        await session.commit()
        return result.rowcount or 0


async def save_open_conversation(
    bot_id: str,
    contact_phone: str,
    connection_id: str | None,
    flow_id: str,
    conversation_json: str,
) -> None:
    """Upsert de la conversación en curso para (bot, contacto) — sin wait_user."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO open_conversations
                    (bot_id, contact_phone, connection_id, flow_id, conversation_json, updated_at)
                VALUES (:bot_id, :contact_phone, :connection_id, :flow_id, :conversation_json, CURRENT_TIMESTAMP)
                ON CONFLICT(bot_id, contact_phone) DO UPDATE SET
                    connection_id=excluded.connection_id,
                    flow_id=excluded.flow_id,
                    conversation_json=excluded.conversation_json,
                    updated_at=CURRENT_TIMESTAMP
            """),
            {
                "bot_id": bot_id, "contact_phone": contact_phone,
                "connection_id": connection_id, "flow_id": flow_id,
                "conversation_json": conversation_json,
            },
        )
        await session.commit()


async def get_open_conversation(bot_id: str, contact_phone: str) -> dict | None:
    """Conversación en curso para (bot, contacto), sin filtro de tiempo — el
    cierre por abandono lo hace prune_open_conversations() aparte."""
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("""
                SELECT flow_id, conversation_json, updated_at
                FROM open_conversations
                WHERE bot_id=:bot_id AND contact_phone=:contact_phone
            """),
            {"bot_id": bot_id, "contact_phone": contact_phone},
        )).fetchone()
    if not row:
        return None
    return {"flow_id": row[0], "conversation_json": row[1], "updated_at": str(row[2])}


async def close_open_conversation(bot_id: str, contact_phone: str) -> None:
    """Cierre explícito (ej. nodo end_conversation) — borra la fila."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("DELETE FROM open_conversations WHERE bot_id=:bot_id AND contact_phone=:contact_phone"),
            {"bot_id": bot_id, "contact_phone": contact_phone},
        )
        await session.commit()


async def prune_open_conversations(max_age_hours: int = 24) -> int:
    """Cierre por abandono — llamado por un proceso aparte (cron externo vía
    /conversations/expire), nunca desde dispatch_message. Retorna cantidad podada."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                DELETE FROM open_conversations
                WHERE updated_at < datetime('now', :cutoff)
            """),
            {"cutoff": f"-{int(max_age_hours)} hours"},
        )
        await session.commit()
        return result.rowcount or 0


async def log_flow_step(
    run_id: str,
    node_id: str,
    node_type: str,
    input_state: str | None,
    output_state: str | None,
    branch_taken: str | None,
    status: str,
    started_at: str,
    ended_at: str,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO flow_run_steps
                  (run_id, node_id, node_type, input_state, output_state,
                   branch_taken, status, started_at, ended_at)
                VALUES
                  (:run_id, :node_id, :node_type, :input_state, :output_state,
                   :branch_taken, :status, :started_at, :ended_at)
            """),
            {
                "run_id": run_id, "node_id": node_id, "node_type": node_type,
                "input_state": input_state, "output_state": output_state,
                "branch_taken": branch_taken, "status": status,
                "started_at": started_at, "ended_at": ended_at,
            },
        )
        await session.commit()


async def insert_metric(
    bot_id: str,
    contact_phone: str,
    contact_name: str,
    canal: str,
    metric_name: str,
    value: str | None,
    metadata: str | None,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO metrics (bot_id, contact_phone, contact_name, canal, metric_name, value, metadata)
                VALUES (:bot_id, :contact_phone, :contact_name, :canal, :metric_name, :value, :metadata)
            """),
            {
                "bot_id": bot_id, "contact_phone": contact_phone, "contact_name": contact_name,
                "canal": canal, "metric_name": metric_name, "value": value, "metadata": metadata,
            },
        )
        await session.commit()


async def get_metrics(bot_id: str, metric_name: str | None = None, limit: int = 200) -> list[dict]:
    async with AsyncSessionLocal() as session:
        if metric_name:
            rows = (await session.execute(
                text("""
                    SELECT id, bot_id, contact_phone, contact_name, canal, metric_name, value, metadata, created_at
                    FROM metrics WHERE bot_id=:bot_id AND metric_name=:metric_name
                    ORDER BY created_at DESC LIMIT :limit
                """),
                {"bot_id": bot_id, "metric_name": metric_name, "limit": limit},
            )).fetchall()
        else:
            rows = (await session.execute(
                text("""
                    SELECT id, bot_id, contact_phone, contact_name, canal, metric_name, value, metadata, created_at
                    FROM metrics WHERE bot_id=:bot_id
                    ORDER BY created_at DESC LIMIT :limit
                """),
                {"bot_id": bot_id, "limit": limit},
            )).fetchall()
    return [
        {
            "id": r[0], "bot_id": r[1], "contact_phone": r[2], "contact_name": r[3],
            "canal": r[4], "metric_name": r[5], "value": r[6], "metadata": r[7],
            "created_at": str(r[8]),
        }
        for r in rows
    ]


async def get_flow_runs(bot_id: str, limit: int = 50) -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("""
                SELECT run_id, flow_id, bot_id, connection_id, started_at, ended_at, status, is_sim
                FROM flow_runs
                WHERE bot_id = :bot_id
                ORDER BY started_at DESC
                LIMIT :limit
            """),
            {"bot_id": bot_id, "limit": limit},
        )).fetchall()
    return [
        {"run_id": r[0], "flow_id": r[1], "bot_id": r[2], "connection_id": r[3],
         "started_at": str(r[4]), "ended_at": str(r[5]) if r[5] else None, "status": r[6],
         "is_sim": bool(r[7])}
        for r in rows
    ]


async def get_flow_run(run_id: str) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(
            text("""
                SELECT run_id, flow_id, bot_id, connection_id,
                       started_at, ended_at, status, trigger_data, is_sim
                FROM flow_runs WHERE run_id=:run_id
            """),
            {"run_id": run_id},
        )).fetchone()
    if not row:
        return None
    return {
        "run_id": row[0], "flow_id": row[1], "bot_id": row[2], "connection_id": row[3],
        "started_at": str(row[4]), "ended_at": str(row[5]) if row[5] else None,
        "status": row[6],
        "trigger_data": _json.loads(row[7]) if row[7] else None,
        "is_sim": bool(row[8]),
    }


async def get_flow_run_steps(run_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text("""
                SELECT id, run_id, node_id, node_type,
                       started_at, ended_at, input_state, output_state, branch_taken, status
                FROM flow_run_steps
                WHERE run_id = :run_id
                ORDER BY id
            """),
            {"run_id": run_id},
        )).fetchall()
    return [
        {
            "id": r[0], "run_id": r[1], "node_id": r[2], "node_type": r[3],
            "started_at": str(r[4]), "ended_at": str(r[5]) if r[5] else None,
            "input_state": _json.loads(r[6]) if r[6] else None,
            "output_state": _json.loads(r[7]) if r[7] else None,
            "branch_taken": r[8], "status": r[9],
        }
        for r in rows
    ]
