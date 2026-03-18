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
