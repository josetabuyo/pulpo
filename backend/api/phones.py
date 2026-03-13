from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.deps import require_admin
from config import load_config, save_config
from state import clients

router = APIRouter()


@router.get("/phones", dependencies=[Depends(require_admin)])
def get_phones():
    config = load_config()
    result = []
    for bot in config.get("bots", []):
        for phone in bot.get("phones", []):
            session_id = phone["number"]
            result.append({
                "botId": bot["id"],
                "botName": bot["name"],
                "number": phone["number"],
                "allowedContacts": phone.get("allowedContacts", []),
                "autoReplyMessage": phone.get("autoReplyMessage") or bot.get("autoReplyMessage"),
                "sessionId": session_id,
                "status": clients.get(session_id, {}).get("status", "stopped"),
            })
    return result


class PhoneCreate(BaseModel):
    botId: str
    botName: str | None = None
    number: str
    allowedContacts: list[str] = []
    autoReplyMessage: str | None = None


@router.post("/phones", dependencies=[Depends(require_admin)], status_code=201)
def create_phone(body: PhoneCreate):
    if not body.botId or not body.number:
        raise HTTPException(status_code=400, detail="botId y number son requeridos")

    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == body.botId), None)

    if not bot:
        if not body.botName or not body.autoReplyMessage:
            raise HTTPException(status_code=400, detail="Bot nuevo requiere botName y autoReplyMessage")
        bot = {"id": body.botId, "name": body.botName, "autoReplyMessage": body.autoReplyMessage, "phones": []}
        config.setdefault("bots", []).append(bot)

    for b in config.get("bots", []):
        if any(p["number"] == body.number for p in b.get("phones", [])):
            raise HTTPException(status_code=409, detail=f'El número ya está en la empresa "{b["name"]}". Movelo desde ahí.')

    entry: dict = {"number": body.number, "allowedContacts": body.allowedContacts}
    if body.autoReplyMessage:
        entry["autoReplyMessage"] = body.autoReplyMessage
    bot.setdefault("phones", []).append(entry)

    save_config(config)
    return {"ok": True, "sessionId": body.number}


class PhoneUpdate(BaseModel):
    allowedContacts: list[str] | None = None
    autoReplyMessage: str | None = None


@router.put("/phones/{number}", dependencies=[Depends(require_admin)])
def update_phone(number: str, body: PhoneUpdate):
    config = load_config()
    for bot in config.get("bots", []):
        phone = next((p for p in bot.get("phones", []) if p["number"] == number), None)
        if phone:
            if body.allowedContacts is not None:
                phone["allowedContacts"] = body.allowedContacts
            if body.autoReplyMessage is not None:
                if body.autoReplyMessage:
                    phone["autoReplyMessage"] = body.autoReplyMessage
                else:
                    phone.pop("autoReplyMessage", None)
            save_config(config)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Número no encontrado")


@router.delete("/phones/{number}", dependencies=[Depends(require_admin)])
def delete_phone(number: str):
    config = load_config()
    for bot in config.get("bots", []):
        idx = next((i for i, p in enumerate(bot.get("phones", [])) if p["number"] == number), None)
        if idx is not None:
            session_id = number
            if session_id in clients:
                try:
                    clients[session_id]["client"].destroy()
                except Exception:
                    pass
                del clients[session_id]
            bot["phones"].pop(idx)
            config["bots"] = [b for b in config["bots"] if b.get("phones")]
            save_config(config)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Número no encontrado")


class MovePhone(BaseModel):
    targetBotId: str


@router.post("/phones/{number}/move", dependencies=[Depends(require_admin)])
def move_phone(number: str, body: MovePhone):
    if not body.targetBotId:
        raise HTTPException(status_code=400, detail="targetBotId requerido")

    config = load_config()
    target_bot = next((b for b in config.get("bots", []) if b["id"] == body.targetBotId), None)
    if not target_bot:
        raise HTTPException(status_code=404, detail="Empresa destino no encontrada")

    source_bot = None
    phone_entry = None
    for b in config.get("bots", []):
        idx = next((i for i, p in enumerate(b.get("phones", [])) if p["number"] == number), None)
        if idx is not None:
            source_bot = b
            phone_entry = b["phones"].pop(idx)
            break

    if not source_bot:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    if source_bot["id"] == body.targetBotId:
        raise HTTPException(status_code=400, detail="El teléfono ya está en esa empresa")

    target_bot.setdefault("phones", []).append(phone_entry)
    save_config(config)
    return {"ok": True, "from": source_bot["id"], "to": body.targetBotId}
