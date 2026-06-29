"""
Business logic for message retrieval.
No FastAPI, no HTTPException, no Pydantic — plain Python types only.
"""

from pulpo.core.db import AsyncSessionLocal
from sqlalchemy import text


async def list_messages(limit: int = 100) -> list[dict]:
    """Returns the last N messages from the DB, ordered by id descending."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(f"SELECT * FROM messages ORDER BY id DESC LIMIT {int(limit)}")
        )
        rows = result.mappings().all()
    return [dict(r) for r in rows]
