"""Endpoints JWT para el portal de empresa."""
import os
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from auth_jwt import (
    check_password,
    create_access_token,
    create_refresh_token,
    refresh_token_expires_at,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from config import load_config
from db import create_session, get_session, revoke_session

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()

COOKIE_NAME = "refresh_token"
COOKIE_MAX_AGE = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600  # segundos


def _find_bot_by_id(config: dict, bot_id: str):
    return next((b for b in config.get("empresas", []) if b["id"] == bot_id), None)


class EmpresaLoginBody(BaseModel):
    bot_id: str
    password: str


_LOGIN_RATE = os.environ.get("LOGIN_RATE_LIMIT", "10/hour")


@router.post("/empresa/login")
@limiter.limit(_LOGIN_RATE)
async def empresa_login(request: Request, response: Response, body: EmpresaLoginBody):
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


@router.post("/empresa/refresh")
async def empresa_refresh(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Sin refresh token")

    session = await get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Refresh token inválido o expirado")

    access_token = create_access_token(session["connection_id"])
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/empresa/logout")
async def empresa_logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await revoke_session(token)

    response.delete_cookie(key=COOKIE_NAME)
    return {"ok": True}


@router.get("/empresa/me")
async def empresa_me(request: Request):
    from middleware_auth import get_empresa_id_from_token
    empresa_id = get_empresa_id_from_token(request)
    if not empresa_id:
        raise HTTPException(status_code=401, detail="Token requerido")

    config = load_config()
    bot = _find_bot_by_id(config, empresa_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    return {"bot_id": bot["id"], "nombre": bot["name"]}
