"""Endpoints del portal cliente — acceso con CLIENT_PASSWORD o ADMIN_PASSWORD."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text

from api.deps import require_client
from config import load_config, save_config
from state import clients
from db import AsyncSessionLocal, log_outbound_message
import sim as sim_engine

router = APIRouter()


def _find_session(config: dict, session_id: str):
    """Returns (bot, item, canonical_id, type). Telegram can be found by tokenId short form."""
    for bot in config.get("bots", []):
        for phone in bot.get("phones", []):
            if phone["number"] == session_id:
                return bot, phone, session_id, "whatsapp"
        for tg in bot.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            canonical = f"{bot['id']}-tg-{token_id}"
            if canonical == session_id or token_id == session_id:
                return bot, tg, canonical, "telegram"
    return None, None, None, None


@router.get("/client/{number}", dependencies=[Depends(require_client)])
def get_client(number: str):
    config = load_config()
    bot, item, canonical, kind = _find_session(config, number)
    if not item:
        raise HTTPException(status_code=404, detail="Número no encontrado")

    status = clients.get(canonical, {}).get("status", "stopped")
    has_own = "autoReplyMessage" in item
    auto_reply = item.get("autoReplyMessage") or bot.get("autoReplyMessage", "")

    return {
        "number": canonical,
        "botName": bot["name"],
        "status": status,
        "autoReplyMessage": auto_reply,
        "hasOwnMessage": has_own,
        "botDefaultMessage": bot.get("autoReplyMessage", ""),
        "type": kind,
    }


class ClientUpdate(BaseModel):
    autoReplyMessage: str


@router.put("/client/{number}", dependencies=[Depends(require_client)])
def update_client(number: str, body: ClientUpdate):
    config = load_config()
    _, item, _, _ = _find_session(config, number)
    if not item:
        raise HTTPException(status_code=404, detail="Número no encontrado")

    if body.autoReplyMessage.strip():
        item["autoReplyMessage"] = body.autoReplyMessage
    else:
        item.pop("autoReplyMessage", None)

    save_config(config)
    return {"ok": True}


@router.get("/client/{number}/messages", dependencies=[Depends(require_client)])
async def get_client_messages(number: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered "
                "FROM messages WHERE bot_phone = :number AND outbound = 0 "
                "ORDER BY timestamp DESC LIMIT 30"
            ),
            {"number": number},
        )
        rows = result.fetchall()
    return [
        {
            "id": r[0],
            "phone": r[1],
            "name": r[2],
            "body": r[3],
            "timestamp": r[4],
            "answered": bool(r[5]),
        }
        for r in rows
    ]


@router.get("/client/{number}/chat/{contact}", dependencies=[Depends(require_client)])
async def get_chat(number: str, contact: str):
    """Historial de mensajes entre el bot y un contacto específico."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered, outbound "
                "FROM messages WHERE bot_phone = :number AND phone = :contact "
                "ORDER BY timestamp ASC LIMIT 100"
            ),
            {"number": number, "contact": contact},
        )
        rows = result.fetchall()
    return [
        {
            "id": r[0],
            "phone": r[1],
            "name": r[2],
            "body": r[3],
            "timestamp": r[4],
            "answered": bool(r[5]),
            "outbound": bool(r[6]),
        }
        for r in rows
    ]


class SendMessageBody(BaseModel):
    text: str


@router.post("/client/{number}/chat/{contact}", dependencies=[Depends(require_client)])
async def send_chat_message(number: str, contact: str, body: SendMessageBody):
    """Envía un mensaje manual desde el bot hacia un contacto."""
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Texto vacío")

    config = load_config()
    bot, _, _, kind = _find_session(config, number)
    if not bot:
        raise HTTPException(status_code=404, detail="Número no encontrado")

    if sim_engine.SIM_MODE:
        await log_outbound_message(bot["id"], number, contact, body.text)
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE messages SET answered = 1 WHERE bot_phone = :number AND phone = :contact AND answered = 0"),
                {"number": number, "contact": contact},
            )
            await session.commit()
        return {"ok": True}

    # Modo real: enviar vía WhatsApp Web
    from state import wa_session
    ok = await wa_session.send_message(number, contact, body.text)
    if not ok:
        raise HTTPException(status_code=503, detail="No se pudo enviar. Verificá que el bot esté conectado.")

    await log_outbound_message(bot["id"], number, contact, body.text)
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE messages SET answered = 1 WHERE bot_phone = :number AND phone = :contact AND answered = 0"),
            {"number": number, "contact": contact},
        )
        await session.commit()
    return {"ok": True}


@router.post("/client/{number}/disconnect", dependencies=[Depends(require_client)])
async def client_disconnect(number: str):
    if sim_engine.SIM_MODE:
        sim_engine.sim_disconnect(number)
    else:
        from state import wa_session
        await wa_session.close_session(number)

    if number in clients:
        clients[number]["status"] = "disconnected"
        clients[number]["qr"] = None

    return {"ok": True}
