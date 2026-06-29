"""Endpoints JWT para el portal de bot."""
import os

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from pulpo.core.auth_jwt import (
    check_password,
    create_access_token,
    create_refresh_token,
    refresh_token_expires_at,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from pulpo.core.config import load_config
from pulpo.core.db import create_session, get_session, revoke_session
from pulpo.interfaces.ui.middleware import get_bot_id_from_token

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()

COOKIE_NAME = "refresh_token"
COOKIE_MAX_AGE = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600  # segundos


def _find_bot_by_id(config: dict, bot_id: str):
    return next((b for b in config.get("bots", []) if b["id"] == bot_id), None)


class BotLoginBody(BaseModel):
    bot_id: str
    password: str


_LOGIN_RATE = os.environ.get("LOGIN_RATE_LIMIT", "10/hour")


@router.post("/bot/login")
@limiter.limit(_LOGIN_RATE)
async def bot_login(request: Request, response: Response, body: BotLoginBody):
    config = load_config()
    bot = _find_bot_by_id(config, body.bot_id)
    if not bot or not check_password(body.password, bot.get("password", "")):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    access_token = create_access_token(body.bot_id)
    refresh_token = create_refresh_token()
    expires_at = refresh_token_expires_at()

    await create_session(body.bot_id, refresh_token, expires_at)

    response.set_cookie(
        key=COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        samesite="strict",
        max_age=COOKIE_MAX_AGE,
    )
    return {"access_token": access_token, "token_type": "bearer", "bot_id": body.bot_id}


@router.post("/bot/refresh")
async def bot_refresh(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Sin refresh token")

    session = await get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Refresh token inválido o expirado")

    access_token = create_access_token(session["connection_id"])
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/bot/logout")
async def bot_logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await revoke_session(token)

    response.delete_cookie(key=COOKIE_NAME)
    return {"ok": True}


@router.get("/bot/me")
async def bot_me(request: Request):
    bot_id = get_bot_id_from_token(request)
    if not bot_id:
        raise HTTPException(status_code=401, detail="Token requerido")

    config = load_config()
    bot = _find_bot_by_id(config, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrada")

    return {"bot_id": bot["id"], "nombre": bot["name"]}
