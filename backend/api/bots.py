from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.deps import require_admin
from config import load_config, save_config
from state import clients

router = APIRouter()


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
                "allowedContacts": phone.get("allowedContacts", []),
                "autoReplyMessage": phone.get("autoReplyMessage"),
                "sessionId": session_id,
                "status": clients.get(session_id, {}).get("status", "stopped"),
            })
        telegram = []
        for tg in bot.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            session_id = f"{bot['id']}-tg-{token_id}"
            telegram.append({
                "tokenId": token_id,
                "allowedContacts": tg.get("allowedContacts", []),
                "autoReplyMessage": tg.get("autoReplyMessage"),
                "sessionId": session_id,
                "status": clients.get(session_id, {}).get("status", "stopped"),
            })
        result.append({
            "id": bot["id"],
            "name": bot["name"],
            "autoReplyMessage": bot.get("autoReplyMessage"),
            "phones": phones,
            "telegram": telegram,
        })
    return result


class BotUpdate(BaseModel):
    name: str | None = None
    autoReplyMessage: str | None = None


@router.put("/bots/{bot_id}", dependencies=[Depends(require_admin)])
def update_bot(bot_id: str, body: BotUpdate):
    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")
    if body.name:
        bot["name"] = body.name
    if body.autoReplyMessage:
        bot["autoReplyMessage"] = body.autoReplyMessage
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
            except Exception:
                pass
            del clients[session_id]

    for tg in bot.get("telegram", []):
        token_id = tg["token"].split(":")[0]
        session_id = f"{bot_id}-tg-{token_id}"
        if session_id in clients:
            try:
                clients[session_id]["client"].stop_polling()
            except Exception:
                pass
            del clients[session_id]

    config["bots"] = [b for b in config["bots"] if b["id"] != bot_id]
    save_config(config)
    return {"ok": True}
