"""
Business logic for the simulator (active when ENABLE_BOTS != 'true').
No FastAPI, no HTTPException, no Pydantic — plain Python types only.
"""

import os

from pulpo.core.config import load_config
from pulpo.core import sim_engine


def get_mode() -> str:
    """Returns 'sim' or 'real' based on ENABLE_BOTS env var."""
    return sim_engine.get_mode()


def sim_connect(number: str) -> dict:
    """
    Marks a simulated WhatsApp session as ready.
    Raises KeyError if the number is not found in config.
    Returns {ok, status, sessionId}.
    """
    config = load_config()
    connection_id = next(
        (
            bot["id"]
            for bot in config.get("bots", [])
            if any(p["number"] == number for p in bot.get("phones", []))
        ),
        None,
    )
    if not connection_id:
        raise KeyError(f"Número no encontrado: {number}")
    sim_engine.sim_connect(number, connection_id)
    return {"ok": True, "status": "ready", "sessionId": number}


def sim_disconnect(number: str) -> dict:
    """
    Disconnects a simulated session.
    Always succeeds (no-op if not connected).
    Returns {ok}.
    """
    sim_engine.sim_disconnect(number)
    return {"ok": True}


async def sim_send(number: str, from_name: str, from_phone: str, text: str) -> dict:
    """
    Simulates receiving a text message and processes it through the flow engine.
    Returns {ok, reply}.
    """
    reply = await sim_engine.sim_receive(number, from_name, from_phone, text)
    return {"ok": True, "reply": reply}


async def sim_send_audio(number: str, from_name: str, from_phone: str, audio_path: str) -> dict:
    """
    Simulates receiving an audio message: transcribes and processes through the flow engine.
    Raises FileNotFoundError if audio_path does not exist.
    Returns {ok, reply}.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"audio_path no existe: {audio_path}")
    reply = await sim_engine.sim_receive(
        number,
        from_name,
        from_phone,
        text="[audio]",
        audio_path=audio_path,
    )
    return {"ok": True, "reply": reply}


def get_conversation(number: str) -> list:
    """Returns the in-memory conversation log for a simulated session."""
    return sim_engine.get_conversation(number)
