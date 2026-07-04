"""
Helpers e2e reutilizables para probar flows reales vía Telegram (teli/Telethon).

Convención de carpetas: tests/e2e/<bot>/test_<flow_slug>.py, marca pytest.mark.e2e.
No reemplaza tests/test_e2e_luganense_teli.py (flow viejo, referencia intacta) —
esa suite queda tal cual; los flows nuevos usan esta infraestructura.
"""
import asyncio
import time
from pathlib import Path

_TELI_DATA = Path("/Users/josetabuyo/Development/teli/data")
_SESSION = str(_TELI_DATA / "sessions" / "user_me")
_API_ID = 31604778
_API_HASH = "385bf75876904b022cb411c1c1954088"


class TeliConversation:
    """
    Conversación multi-turno contra un bot real de Telegram usando la cuenta
    personal del usuario (Telethon). A diferencia del helper de un solo turno
    de test_e2e_luganense_teli.py, mantiene el client abierto entre sends para
    soportar escenarios con varios mensajes seguidos (aclaración, dirección).
    """

    def __init__(self, bot_username: str):
        self._bot_username = bot_username
        self._client = None
        self._bot_entity = None
        self._bot_id = None

    async def __aenter__(self) -> "TeliConversation":
        from telethon import TelegramClient

        self._client = TelegramClient(_SESSION, _API_ID, _API_HASH)
        await self._client.start()
        self._bot_entity = await self._client.get_entity(self._bot_username)
        self._bot_id = self._bot_entity.id
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.disconnect()

    async def send_and_wait(self, message: str, timeout: int = 180, settle: int = 15) -> str | None:
        """Envía `message` y devuelve el ÚLTIMO reply del bot (estrategia settle-time)."""
        replies = await self.send_and_collect(message, timeout=timeout, settle=settle)
        return replies[-1] if replies else None

    async def send_and_collect(self, message: str, timeout: int = 180, settle: int = 15) -> list[str]:
        """Envía `message` y devuelve TODOS los replies del bot dentro del timeout."""
        sent = await self._client.send_message(self._bot_username, message)
        last_seen_id = sent.id
        collected: list[str] = []
        first_reply_at: float | None = None
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            await asyncio.sleep(5)
            new_msgs = await self._client.get_messages(self._bot_entity, limit=30, min_id=last_seen_id)
            fresh = [
                m for m in sorted(new_msgs, key=lambda m: m.id)
                if m.sender_id == self._bot_id and m.text
            ]
            for m in fresh:
                collected.append(m.text)
                last_seen_id = m.id
            if collected and first_reply_at is None:
                first_reply_at = time.monotonic()
            if first_reply_at is not None and (time.monotonic() - first_reply_at) >= settle:
                break

        return collected
