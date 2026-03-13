from fastapi import APIRouter, Depends
from sqlalchemy import text

from api.deps import require_admin
from db import AsyncSessionLocal

router = APIRouter()


@router.get("/messages", dependencies=[Depends(require_admin)])
async def get_messages():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT * FROM messages ORDER BY id DESC LIMIT 100")
        )
        rows = result.mappings().all()
    return [dict(r) for r in rows]
