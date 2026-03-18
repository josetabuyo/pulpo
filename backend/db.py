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
                UNIQUE(type, value)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contact_channels_contact_id ON contact_channels(contact_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_contact_channels_lookup ON contact_channels(type, value)"
        ))


async def log_message(bot_id: str, bot_phone: str, phone: str, name: str | None, body: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("INSERT INTO messages (bot_id, bot_phone, phone, name, body) VALUES (:bot_id, :bot_phone, :phone, :name, :body)"),
            {"bot_id": bot_id, "bot_phone": bot_phone, "phone": phone, "name": name, "body": body},
        )
        await session.commit()
        return result.lastrowid


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
        text(f"SELECT id, contact_id, type, value FROM contact_channels WHERE contact_id IN ({placeholders})"),
        params,
    )).fetchall()
    result: dict[int, list] = {cid: [] for cid in contact_ids}
    for row in rows:
        result[row[1]].append({"id": row[0], "type": row[2], "value": row[3]})
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


async def add_channel(contact_id: int, type: str, value: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("INSERT INTO contact_channels (contact_id, type, value) VALUES (:contact_id, :type, :value)"),
            {"contact_id": contact_id, "type": type, "value": value},
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
        row = (await session.execute(
            text("SELECT contact_id FROM contact_channels WHERE type = :type AND value = :value"),
            {"type": type, "value": value},
        )).fetchone()
        if not row:
            return None
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
