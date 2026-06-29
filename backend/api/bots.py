import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.deps import require_admin
from config import load_config, save_config
from state import clients, wavi_status

logger = logging.getLogger(__name__)

router = APIRouter()


class BotCreate(BaseModel):
    id: str
    name: str
    password: str


@router.post("/bots", dependencies=[Depends(require_admin)], status_code=201)
def create_bot(body: BotCreate):
    if not body.id.strip() or not body.name.strip() or not body.password.strip():
        raise HTTPException(status_code=400, detail="id, name y password son requeridos")
    config = load_config()
    if any(b["id"] == body.id for b in config.get("bots", [])):
        raise HTTPException(status_code=409, detail="Ya existe una bot con ese id")
    config.setdefault("bots", []).append({
        "id": body.id,
        "name": body.name,
        "password": body.password,
        "phones": [],
        "telegram": [],
    })
    save_config(config)
    return {"ok": True, "id": body.id}


@router.get("/bots", dependencies=[Depends(require_admin)])
def get_bots():
    config = load_config()
    result = []
    for bot in config.get("bots", []):
        phones = []
        for phone in bot.get("phones", []):
            session_id = phone["number"]
            phones.append({
                "number": phone["number"],
                "sessionId": session_id,
                "status": wavi_status.get(session_id, "stopped"),
                "allowMass": phone.get("allow_mass", False),
            })
        telegram = []
        for tg in bot.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            session_id = f"{bot['id']}-tg-{token_id}"
            tg_client = clients.get(session_id, {})
            telegram.append({
                "tokenId": token_id,
                "sessionId": session_id,
                "status": tg_client.get("status", "stopped"),
                "username": tg_client.get("bot_username", ""),
                "botName": tg_client.get("bot_name", ""),
                "allowMass": tg.get("allow_mass", False),
            })
        result.append({
            "id": bot["id"],
            "name": bot["name"],
            "phones": phones,
            "telegram": telegram,
        })
    return result


class TelegramSettingsPatch(BaseModel):
    allow_mass: bool


@router.patch("/bots/{bot_id}/telegram/{token_id}/settings", dependencies=[Depends(require_admin)])
def patch_telegram_settings(bot_id: str, token_id: str, body: TelegramSettingsPatch):
    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")
    for tg in bot.get("telegram", []):
        if tg["token"].split(":")[0] == token_id:
            tg["allow_mass"] = body.allow_mass
            save_config(config)
            return {"ok": True, "allow_mass": body.allow_mass}
    raise HTTPException(status_code=404, detail="Conexión Telegram no encontrada")


class BotUpdate(BaseModel):
    name: str | None = None


@router.put("/bots/{bot_id}", dependencies=[Depends(require_admin)])
def update_bot(bot_id: str, body: BotUpdate):
    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")
    if body.name:
        bot["name"] = body.name
    save_config(config)
    return {"ok": True}


@router.delete("/bots/{bot_id}", dependencies=[Depends(require_admin)])
def delete_bot(bot_id: str):
    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    for phone in bot.get("phones", []):
        session_id = phone["number"]
        if session_id in clients:
            try:
                clients[session_id]["client"].destroy()
            except Exception as e:
                logger.warning("[bots] destroy de %s falló: %s", session_id, e)
            del clients[session_id]

    for tg in bot.get("telegram", []):
        token_id = tg["token"].split(":")[0]
        session_id = f"{bot_id}-tg-{token_id}"
        if session_id in clients:
            try:
                clients[session_id]["client"].stop_polling()
            except Exception as e:
                logger.warning("[bots] stop_polling de %s falló: %s", session_id, e)
            del clients[session_id]

    config["bots"] = [b for b in config["bots"] if b["id"] != bot_id]
    save_config(config)
    return {"ok": True}
