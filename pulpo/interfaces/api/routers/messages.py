"""
Router: /messages

Thin FastAPI wrapper over the business layer. No auth — auth is applied
by interfaces/ui/app.py at mount time.
"""
from fastapi import APIRouter, HTTPException

from pulpo.business import messages as messages_svc

router = APIRouter()


@router.get("")
async def get_messages():
    try:
        return await messages_svc.list_messages()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
