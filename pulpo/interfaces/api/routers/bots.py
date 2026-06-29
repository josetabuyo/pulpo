"""
Router: /bots

Thin FastAPI wrapper over the business layer. No auth — auth is applied
by interfaces/ui/app.py at mount time.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pulpo.business import bots as bots_svc

logger = logging.getLogger(__name__)

router = APIRouter()


class BotCreate(BaseModel):
    id: str
    name: str
    password: str


@router.post("", status_code=201)
def create_bot(body: BotCreate):
    if not body.id.strip() or not body.name.strip() or not body.password.strip():
        raise HTTPException(status_code=400, detail="id, name y password son requeridos")
    try:
        return bots_svc.create_bot(
            bot_id=body.id,
            name=body.name,
            password=body.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("")
def get_bots():
    try:
        return bots_svc.list_bots()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class TelegramSettingsPatch(BaseModel):
    allow_mass: bool


@router.patch("/{bot_id}/telegram/{token_id}/settings")
def patch_telegram_settings(bot_id: str, token_id: str, body: TelegramSettingsPatch):
    try:
        return bots_svc.patch_telegram_settings(
            bot_id=bot_id,
            token_id=token_id,
            allow_mass=body.allow_mass,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


class BotUpdate(BaseModel):
    name: str | None = None


@router.put("/{bot_id}")
def update_bot(bot_id: str, body: BotUpdate):
    try:
        return bots_svc.update_bot(bot_id=bot_id, name=body.name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{bot_id}")
def delete_bot(bot_id: str):
    try:
        return bots_svc.delete_bot(bot_id=bot_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
