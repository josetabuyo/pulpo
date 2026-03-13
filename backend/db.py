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
                answered  INTEGER DEFAULT 0
            )
        """))


async def log_message(bot_id: str, bot_phone: str, phone: str, name: str | None, body: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("INSERT INTO messages (bot_id, bot_phone, phone, name, body) VALUES (:bot_id, :bot_phone, :phone, :name, :body)"),
            {"bot_id": bot_id, "bot_phone": bot_phone, "phone": phone, "name": name, "body": body},
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
