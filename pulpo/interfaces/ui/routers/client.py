"""Endpoints del portal cliente — acceso con CLIENT_PASSWORD o ADMIN_PASSWORD."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text

from pulpo.interfaces.ui.deps import require_client
from pulpo.core.config import load_config, save_config
from pulpo.core.state import clients
from pulpo.core.db import AsyncSessionLocal, log_outbound_message
from pulpo.core import sim_engine

router = APIRouter()


def _find_session(config: dict, session_id: str):
    """Returns (bot, item, canonical_id, type). Finds Telegram sessions by tokenId short form."""
    for bot in config.get("bots", []):
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

    return {
        "number": canonical,
        "botName": bot["name"],
        "status": status,
        "type": kind,
    }


@router.get("/client/{number}/messages", dependencies=[Depends(require_client)])
async def get_client_messages(number: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered "
                "FROM messages WHERE connection_phone = :number AND outbound = 0 "
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


@router.get("/client/{number}/history/{contact}", dependencies=[Depends(require_client)])
async def get_chat(number: str, contact: str):
    """Historial de mensajes entre el bot y un contacto específico."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered, outbound "
                "FROM messages WHERE connection_phone = :number AND phone = :contact "
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


@router.post("/client/{number}/history/{contact}", dependencies=[Depends(require_client)])
async def send_chat_message(number: str, contact: str, body: SendMessageBody):
    """Envía un mensaje manual desde el bot hacia un contacto."""
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Texto vacío")

    config = load_config()
    bot, _, _, kind = _find_session(config, number)
    if not bot:
        raise HTTPException(status_code=404, detail="Número no encontrado")

    def _accumulate_outbound(bot_id: str, contact: str, msg_text: str) -> None:
        from pulpo.graphs.nodes.summarize import accumulate as _acc
        _acc(bot_id=bot_id, contact_phone=contact, contact_name=contact,
             msg_type="text", content=f"Tú: {msg_text}")

    if sim_engine.SIM_MODE:
        await log_outbound_message(bot["id"], number, contact, body.text)
        _accumulate_outbound(bot["id"], contact, body.text)
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE messages SET answered = 1 WHERE connection_phone = :number AND phone = :contact AND answered = 0"),
                {"number": number, "contact": contact},
            )
            await session.commit()
        return {"ok": True}

    tg_client = clients.get(number)
    if not tg_client:
        raise HTTPException(status_code=503, detail="Bot de Telegram no está activo")
    try:
        await tg_client["client"].bot.send_message(chat_id=int(contact), text=body.text)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"No se pudo enviar por Telegram: {e}")

    await log_outbound_message(bot["id"], number, contact, body.text)
    _accumulate_outbound(bot["id"], contact, body.text)
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE messages SET answered = 1 WHERE connection_phone = :number AND phone = :contact AND answered = 0"),
            {"number": number, "contact": contact},
        )
        await session.commit()
    return {"ok": True}


@router.post("/client/{number}/disconnect", dependencies=[Depends(require_client)])
async def client_disconnect(number: str):
    sim = _sim()
    if sim.SIM_MODE:
        sim.sim_disconnect(number)

    clients.pop(number, None)
    return {"ok": True}
