"""
WhatsAppV2Manager — adapter para OpenWA (@open-wa/wa-automate).

Mantiene un dict de instancias OpenWA (un proceso Node.js por teléfono).
Recibe webhooks (mensajes y eventos de ciclo de vida) y los procesa.
"""
import asyncio
import base64
import logging
import signal
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_PORT = 8090
_SESSIONS_DIR = Path(__file__).parent.parent.parent / "data" / "wa-v2-sessions"

# Estados de ciclo de vida que OpenWA puede emitir
_OPENWA_READY_STATES = {"CONNECTED", "authenticated", "ready"}


class _Instance:
    def __init__(self, phone: str, port: int, process: asyncio.subprocess.Process):
        self.phone = phone
        self.port = port
        self.process = process


class WhatsAppV2Manager:
    def __init__(self):
        self._instances: dict[str, _Instance] = {}
        # Estado de ciclo de vida por phone: "connecting" / "qr_ready" / "ready" / "disconnected"
        self._states: dict[str, str] = {}
        # QR base64 más reciente por phone (None cuando ya no aplica)
        self._qr_store: dict[str, Optional[str]] = {}

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
            "--qr-format", "image",   # QR como imagen base64 en el webhook
        ]

        self._states[phone] = "connecting"
        self._qr_store[phone] = None

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
        # Proceso terminó
        if self._states.get(phone) not in ("ready",):
            self._states[phone] = "disconnected"

    async def stop_instance(self, phone: str) -> None:
        inst = self._instances.pop(phone, None)
        self._states.pop(phone, None)
        self._qr_store.pop(phone, None)
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

    def get_state(self, phone: str) -> str:
        if phone not in self._instances and phone not in self._states:
            return "stopped"
        return self._states.get(phone, "stopped")

    def get_qr(self, phone: str) -> dict:
        state = self.get_state(phone)
        qr = self._qr_store.get(phone)
        result: dict = {"status": state}
        if qr:
            result["qr"] = qr
        return result

    def status(self) -> list[dict]:
        phones = set(self._instances.keys()) | set(self._states.keys())
        return [
            {
                "phone": phone,
                "port": self._instances[phone].port if phone in self._instances else None,
                "pid": self._instances[phone].process.pid if phone in self._instances else None,
                "state": self._states.get(phone, "stopped"),
            }
            for phone in phones
        ]

    # ── REST OpenWA ──────────────────────────────────────────────────────────

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

    async def get_history(self, phone: str, contact_jid: str, count: int = 0) -> list[dict]:
        """count=0 → todos los mensajes."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                self._url(phone, "/api/getAllMessagesInChat"),
                params={"chatId": contact_jid, "includeMe": "true", "includeNotifications": "false"},
            )
            r.raise_for_status()
            msgs = r.json().get("response", [])
            return msgs if not count else msgs[-count:]

    # ── Webhook handler ──────────────────────────────────────────────────────

    async def handle_webhook(self, payload: dict) -> None:
        """
        Despacha eventos de OpenWA:
          - qr / QR           → guarda QR, estado = qr_ready
          - authenticated / CONNECTED / ready → estado = ready, limpia QR
          - CONFLICT / disconnected           → estado = disconnected
          - mensaje (has "body")              → run_flows()
        """
        session_id = payload.get("sessionId", "")
        event = payload.get("event") or payload.get("dataType") or ""

        # ── Eventos de ciclo de vida ─────────────────────────────────────────
        if event in ("qr", "QR") or "qr" in (payload.keys() & {"qr"}):
            qr_data = payload.get("qr") or payload.get("data", "")
            if qr_data and session_id:
                self._qr_store[session_id] = qr_data
                self._states[session_id] = "qr_ready"
                logger.info("[wa-v2] QR listo para %s", session_id)
            return

        if event in _OPENWA_READY_STATES or payload.get("state") in _OPENWA_READY_STATES:
            if session_id:
                self._states[session_id] = "ready"
                self._qr_store[session_id] = None
                logger.info("[wa-v2] Instancia %s conectada", session_id)
            return

        if event in ("CONFLICT", "disconnected", "UNPAIRED"):
            if session_id:
                self._states[session_id] = "disconnected"
                logger.info("[wa-v2] Instancia %s desconectada (event=%s)", session_id, event)
            return

        # ── Mensajes ─────────────────────────────────────────────────────────
        if payload.get("fromMe"):
            return

        # Si no tiene "from" probablemente es un evento desconocido — ignorar
        if not payload.get("from"):
            logger.debug("[wa-v2] Payload sin 'from' ignorado: event=%r", event)
            return

        await self._handle_message(payload)

    async def _handle_message(self, payload: dict) -> None:
        session_id = payload.get("sessionId", "")
        from_jid   = payload.get("from", "")
        msg_type   = payload.get("type", "chat")
        body       = payload.get("body", "")
        sender     = payload.get("sender") or {}
        contact_name = sender.get("pushname", "")
        ts = payload.get("t")
        timestamp = datetime.fromtimestamp(ts) if ts else None

        contact_phone = from_jid.replace("@c.us", "").replace("@g.us", "")
        bot_phone = session_id

        message_type: str = "text"
        attachment_path: Optional[str] = None

        if msg_type == "ptt" and body:
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
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=_SESSIONS_DIR)
    tmp.write(base64.b64decode(data))
    tmp.close()
    return tmp.name


# Singleton global
wa_v2_manager = WhatsAppV2Manager()
