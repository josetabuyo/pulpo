import re
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.deps import require_admin, require_client
from config import load_config, save_config
from state import clients

router = APIRouter()


class TelegramCreate(BaseModel):
    botId: str
    token: str
    allowedContacts: list[str] = []
    autoReplyMessage: str | None = None


@router.post("/telegram", dependencies=[Depends(require_admin)], status_code=201)
def add_telegram(body: TelegramCreate):
    if not body.botId or not body.token:
        raise HTTPException(status_code=400, detail="botId y token son requeridos")
    if not re.match(r"^\d+:[A-Za-z0-9_-]+$", body.token):
        raise HTTPException(status_code=400, detail="Formato de token inválido (debe ser número:cadena)")

    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == body.botId), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    token_id = body.token.split(":")[0]
    bot.setdefault("telegram", [])
    if any(t["token"].split(":")[0] == token_id for t in bot["telegram"]):
        raise HTTPException(status_code=409, detail="Este token ya está registrado")

    entry: dict = {"token": body.token, "allowedContacts": body.allowedContacts}
    if body.autoReplyMessage:
        entry["autoReplyMessage"] = body.autoReplyMessage
    bot["telegram"].append(entry)
    save_config(config)

    session_id = f"{body.botId}-tg-{token_id}"
    clients[session_id] = {"status": "stopped", "qr": None, "bot_id": body.botId, "type": "telegram", "client": None}

    return {"ok": True, "tokenId": token_id, "sessionId": session_id}


class TelegramUpdate(BaseModel):
    allowedContacts: list[str] | None = None
    autoReplyMessage: str | None = None


@router.put("/telegram/{token_id}", dependencies=[Depends(require_admin)])
def update_telegram(token_id: str, body: TelegramUpdate):
    config = load_config()
    for bot in config.get("bots", []):
        tg = next((t for t in bot.get("telegram", []) if t["token"].split(":")[0] == token_id), None)
        if tg:
            if body.allowedContacts is not None:
                tg["allowedContacts"] = body.allowedContacts
            if body.autoReplyMessage is not None:
                if body.autoReplyMessage:
                    tg["autoReplyMessage"] = body.autoReplyMessage
                else:
                    tg.pop("autoReplyMessage", None)
            save_config(config)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Token no encontrado")


@router.delete("/telegram/{token_id}", dependencies=[Depends(require_admin)])
def delete_telegram(token_id: str):
    config = load_config()
    for bot in config.get("bots", []):
        idx = next(
            (i for i, t in enumerate(bot.get("telegram", [])) if t["token"].split(":")[0] == token_id),
            None,
        )
        if idx is not None:
            session_id = f"{bot['id']}-tg-{token_id}"
            if session_id in clients:
                try:
                    clients[session_id]["client"].stop_polling()
                except Exception:
                    pass
                del clients[session_id]
            bot["telegram"].pop(idx)
            save_config(config)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Token no encontrado")


class MoveTelegram(BaseModel):
    targetBotId: str


@router.post("/telegram/{token_id}/move", dependencies=[Depends(require_admin)])
def move_telegram(token_id: str, body: MoveTelegram):
    if not body.targetBotId:
        raise HTTPException(status_code=400, detail="targetBotId requerido")

    config = load_config()
    target_bot = next((b for b in config.get("bots", []) if b["id"] == body.targetBotId), None)
    if not target_bot:
        raise HTTPException(status_code=404, detail="Empresa destino no encontrada")

    source_bot = None
    tg_entry = None
    for b in config.get("bots", []):
        idx = next(
            (i for i, t in enumerate(b.get("telegram", [])) if t["token"].split(":")[0] == token_id),
            None,
        )
        if idx is not None:
            source_bot = b
            tg_entry = b["telegram"].pop(idx)
            break

    if not source_bot:
        raise HTTPException(status_code=404, detail="Bot de Telegram no encontrado")
    if source_bot["id"] == body.targetBotId:
        raise HTTPException(status_code=400, detail="Ya está en esa empresa")

    target_bot.setdefault("telegram", []).append(tg_entry)

    old_session_id = f"{source_bot['id']}-tg-{token_id}"
    new_session_id = f"{body.targetBotId}-tg-{token_id}"
    if old_session_id in clients:
        clients[new_session_id] = clients.pop(old_session_id)
        clients[new_session_id]["bot_id"] = body.targetBotId

    save_config(config)
    return {"ok": True, "from": source_bot["id"], "to": body.targetBotId}


@router.post("/telegram/connect/{token_id}", dependencies=[Depends(require_client)])
def connect_telegram(token_id: str):
    config = load_config()
    found = None
    for bot in config.get("bots", []):
        tg = next((t for t in bot.get("telegram", []) if t["token"].split(":")[0] == token_id), None)
        if tg:
            found = {"bot_id": bot["id"], "token": tg["token"], "session_id": f"{bot['id']}-tg-{token_id}"}
            break

    if not found:
        raise HTTPException(status_code=404, detail="Token no encontrado")

    session_id = found["session_id"]
    existing = clients.get(session_id, {})
    if existing.get("status") in ("connecting", "ready"):
        return {"ok": True, "status": existing["status"], "sessionId": session_id}

    # En Python los bots de Telegram se arrancan al inicio del proceso.
    # Este endpoint indica que el bot está "running" si existe en clients.
    status = existing.get("status", "stopped")
    return {"ok": True, "status": status, "sessionId": session_id}
