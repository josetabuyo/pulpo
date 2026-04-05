from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sim as sim_engine

router = APIRouter()


@router.get("/mode")
def get_mode():
    return {"mode": sim_engine.get_mode()}


@router.post("/sim/connect/{number}")
async def sim_connect(number: str):
    from config import load_config
    config = load_config()
    connection_id = next(
        (bot["id"] for bot in config.get("empresas", [])
         if any(p["number"] == number for p in bot.get("phones", []))),
        None,
    )
    if not connection_id:
        raise HTTPException(status_code=404, detail="Número no encontrado.")
    sim_engine.sim_connect(number, connection_id)
    return {"ok": True, "status": "ready", "sessionId": number}


@router.post("/sim/disconnect/{number}")
async def sim_disconnect(number: str):
    sim_engine.sim_disconnect(number)
    return {"ok": True}


class SimSendBody(BaseModel):
    from_name: str = "Contacto"
    from_phone: str = "0000000000"
    text: str


@router.post("/sim/send/{number}")
async def sim_send(number: str, body: SimSendBody):
    reply = await sim_engine.sim_receive(number, body.from_name, body.from_phone, body.text)
    return {"ok": True, "reply": reply}


class SimSendAudioBody(BaseModel):
    from_name: str = "Contacto"
    from_phone: str = "0000000000"
    audio_path: str


@router.post("/sim/send-audio/{number}")
async def sim_send_audio(number: str, body: SimSendAudioBody):
    """Simula la recepción de un mensaje de audio: transcribe y acumula en sumarizadoras."""
    import os
    if not os.path.exists(body.audio_path):
        raise HTTPException(status_code=400, detail=f"audio_path no existe: {body.audio_path}")
    reply = await sim_engine.sim_receive(
        number,
        body.from_name,
        body.from_phone,
        text="[audio]",
        audio_path=body.audio_path,
    )
    return {"ok": True, "reply": reply}


@router.get("/sim/messages/{number}")
def sim_messages(number: str):
    return sim_engine.get_conversation(number)
