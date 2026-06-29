"""
Router: /sim

Thin FastAPI wrapper over the business layer. No auth — auth is applied
by interfaces/ui/app.py at mount time.

Also includes GET /mode (no prefix) for simulator mode detection.

Route layout (parent mounts at /sim):
  GET  /mode          ← no-prefix route, exposed under /sim/mode
  POST /connect/{number}
  POST /disconnect/{number}
  POST /send/{number}
  POST /send-audio/{number}
  GET  /messages/{number}
"""
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pulpo.business import sim as sim_svc

router = APIRouter()


@router.get("/mode")
def get_mode():
    try:
        return sim_svc.get_mode()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/connect/{number}")
async def sim_connect(number: str):
    try:
        return await sim_svc.sim_connect(number=number)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/disconnect/{number}")
async def sim_disconnect(number: str):
    try:
        return await sim_svc.sim_disconnect(number=number)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SimSendBody(BaseModel):
    from_name: str = "Contacto"
    from_phone: str = "0000000000"
    text: str


@router.post("/send/{number}")
async def sim_send(number: str, body: SimSendBody):
    try:
        return await sim_svc.sim_send(
            number=number,
            from_name=body.from_name,
            from_phone=body.from_phone,
            text=body.text,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SimSendAudioBody(BaseModel):
    from_name: str = "Contacto"
    from_phone: str = "0000000000"
    audio_path: str


@router.post("/send-audio/{number}")
async def sim_send_audio(number: str, body: SimSendAudioBody):
    """Simula la recepción de un mensaje de audio: transcribe y acumula en sumarizadoras."""
    if not os.path.exists(body.audio_path):
        raise HTTPException(status_code=400, detail=f"audio_path no existe: {body.audio_path}")
    try:
        return await sim_svc.sim_send_audio(
            number=number,
            from_name=body.from_name,
            from_phone=body.from_phone,
            audio_path=body.audio_path,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/messages/{number}")
def sim_messages(number: str):
    try:
        return sim_svc.get_conversation(number=number)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
