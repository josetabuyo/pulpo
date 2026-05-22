"""
WhatsAppV2Manager — adapter para OpenWA (@open-wa/wa-automate).

Mantiene un dict de instancias OpenWA (un proceso Node.js por teléfono).
Recibe webhooks y los normaliza a FlowState para pasarlos al engine.
"""
import asyncio
import base64
import logging
import os
import signal
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Puerto base para instancias OpenWA (teléfono 0 → 8090, 1 → 8091, ...)
_BASE_PORT = 8090

# Directorio donde OpenWA guarda las sesiones
_SESSIONS_DIR = Path(__file__).parent.parent.parent / "data" / "wa-v2-sessions"


class _Instance:
    def __init__(self, phone: str, port: int, process: asyncio.subprocess.Process):
        self.phone = phone
        self.port = port
        self.process = process


class WhatsAppV2Manager:
    def __init__(self):
        self._instances: dict[str, _Instance] = {}

    # ── Gestión de instancias ────────────────────────────────────────────────

    async def start_instance(self, phone: str, port: int, webhook_url: str) -> None:
        if phone in self._instances:
            logger.info("[wa-v2] Instancia %s ya activa en puerto %d", phone, self._instances[phone].port)
            return

        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

        cmd = [
            "npx", "@open-wa/wa-automate",
            "--session-id", phone,
            "--port", str(port),
            "--webhook", webhook_url,
            "--headless", "true",
            "--session-data-path", str(_SESSIONS_DIR),
            "--log-level", "info",
            "--disable-spins", "true",
        ]

        logger.info("[wa-v2] Iniciando instancia %s en puerto %d", phone, port)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._instances[phone] = _Instance(phone=phone, port=port, process=process)
        asyncio.create_task(self._log_output(phone, process))

    async def _log_output(self, phone: str, process: asyncio.subprocess.Process) -> None:
        if process.stdout is None:
            return
        async for line in process.stdout:
            logger.info("[wa-v2:%s] %s", phone, line.decode(errors="replace").rstrip())

    async def stop_instance(self, phone: str) -> None:
        inst = self._instances.pop(phone, None)
        if not inst:
            return
        try:
            inst.process.send_signal(signal.SIGTERM)
            await asyncio.wait_for(inst.process.wait(), timeout=10)
        except (ProcessLookupError, asyncio.TimeoutError):
            pass
        logger.info("[wa-v2] Instancia %s detenida", phone)

    async def stop_all(self) -> None:
        for phone in list(self._instances.keys()):
            await self.stop_instance(phone)

    def status(self) -> list[dict]:
        return [
            {"phone": inst.phone, "port": inst.port, "pid": inst.process.pid}
            for inst in self._instances.values()
        ]

    # ── REST OpenWA ─────────────────────────────────────────────────────────

    def _url(self, phone: str, path: str) -> str:
        inst = self._instances.get(phone)
        if not inst:
            raise ValueError(f"Instancia {phone} no activa")
        return f"http://localhost:{inst.port}{path}"

    async def send_message(self, phone: str, to_number: str, text: str) -> dict:
        to_jid = f"{to_number}@c.us"
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                self._url(phone, "/api/sendText"),
                json={"to": to_jid, "content": text},
            )
            r.raise_for_status()
            return r.json()

    async def get_history(self, phone: str, contact_jid: str, count: int = 100) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                self._url(phone, f"/api/getAllMessagesInChat"),
                params={"chatId": contact_jid, "includeMe": "true", "includeNotifications": "false"},
            )
            r.raise_for_status()
            msgs = r.json().get("response", [])
            return msgs[-count:]

    # ── Webhook handler ──────────────────────────────────────────────────────

    async def handle_webhook(self, payload: dict) -> None:
        """
        Normaliza payload de OpenWA → FlowState y ejecuta run_flows().

        Payload relevante:
          payload["from"]               → JID remitente "5491155...@c.us"
          payload["body"]               → texto o base64 (si --auto-download)
          payload["type"]               → "chat" | "ptt" | "image" | "document"
          payload["isGroupMsg"]         → bool
          payload["sender"]["pushname"] → nombre del contacto
          payload["t"]                  → timestamp unix
          payload["fromMe"]             → ignorar si True
          payload["sessionId"]          → phone del bot
        """
        if payload.get("fromMe"):
            return

        session_id = payload.get("sessionId", "")
        from_jid = payload.get("from", "")
        msg_type = payload.get("type", "chat")
        body = payload.get("body", "")
        sender = payload.get("sender") or {}
        contact_name = sender.get("pushname", "")
        ts = payload.get("t")
        timestamp = datetime.fromtimestamp(ts) if ts else None

        contact_phone = from_jid.replace("@c.us", "").replace("@g.us", "")
        bot_phone = session_id

        # Determinar tipo de mensaje y adjunto
        message_type = "text"
        attachment_path: Optional[str] = None

        if msg_type == "ptt" and body:
            # Base64 ogg — guardar como archivo temporal para TranscribeAudioNode
            message_type = "audio"
            attachment_path = await _save_base64(body, suffix=".ogg")
            body = ""
        elif msg_type == "image" and body:
            message_type = "image"
            attachment_path = await _save_base64(body, suffix=".jpg")
            body = ""
        elif msg_type == "document" and body:
            message_type = "document"
            filename = payload.get("filename", "document")
            ext = Path(filename).suffix or ".bin"
            attachment_path = await _save_base64(body, suffix=ext)
            body = filename

        from graphs.nodes.state import FlowState
        state = FlowState(
            canal="whatsapp_v2",
            message=body,
            message_type=message_type,
            attachment_path=attachment_path,
            contact_phone=contact_phone,
            contact_name=contact_name,
            connection_id=bot_phone,
            timestamp=timestamp,
        )

        logger.info("[wa-v2] Mensaje de %s → bot %s: type=%s", contact_phone, bot_phone, msg_type)

        from graphs.compiler import run_flows
        await run_flows(state, connection_id=bot_phone)


async def _save_base64(data: str, suffix: str) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=_SESSIONS_DIR)
    tmp.write(base64.b64decode(data))
    tmp.close()
    return tmp.name


# Singleton global
wa_v2_manager = WhatsAppV2Manager()
