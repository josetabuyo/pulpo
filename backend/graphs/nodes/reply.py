"""
SendMessageNode — único nodo que envía mensajes.

Si `to` está vacío → escribe en state.reply (el adapter lo envía al usuario).
Si `to` tiene valor → envía inmediatamente al destinatario via Telegram o WA.

Config:
  to:      str  — destinatario. Vacío = usuario de la conversación.
                  Soporta placeholders: "{{worker_telegram_id}}", "{{contact_phone}}", etc.
  message: str  — texto con placeholders.
  channel: str  — "auto" | "telegram" | "whatsapp"  (default: "auto")
                  auto: numérico → telegram, con + o 10+ dígitos → whatsapp
"""
import logging
from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)


class SendMessageNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        if state.from_delta_sync:
            return state

        to      = interpolate(self.config.get("to", ""), state).strip()
        message = interpolate(self.config.get("message", ""), state)
        channel = self.config.get("channel", "auto")

        if not to:
            state.reply = message
            return state

        await self._send(to, message, channel, state)
        return state

    async def _send(self, to: str, message: str, channel: str, state: FlowState) -> None:
        if channel == "auto":
            channel = "telegram" if to.lstrip("-").isdigit() else "whatsapp"

        if channel == "telegram":
            await self._send_telegram(to, message, state.empresa_id)
        elif channel == "whatsapp":
            await self._send_whatsapp(to, message, state.connection_id)
        else:
            logger.warning("[SendMessageNode] canal desconocido: %s", channel)

    async def _send_telegram(self, chat_id: str, message: str, empresa_id: str) -> None:
        import os
        if os.getenv("ENABLE_BOTS", "false").lower() != "true":
            logger.info("[SendMessageNode] [sim] TG → %s: %s", chat_id, message[:80])
            return

        from state import clients
        tg_session = next(
            (k for k, v in clients.items()
             if v.get("connection_id") == empresa_id
             and v.get("type") == "telegram"
             and v.get("client")),
            None,
        )
        if not tg_session:
            logger.warning("[SendMessageNode] Sin bot Telegram activo para empresa '%s'", empresa_id)
            return

        try:
            await clients[tg_session]["client"].bot.send_message(
                chat_id=int(chat_id), text=message, parse_mode="Markdown",
            )
            logger.info("[SendMessageNode] TG → %s enviado", chat_id)
        except Exception as e:
            logger.error("[SendMessageNode] Error TG → %s: %s", chat_id, e)

    async def _send_whatsapp(self, to: str, message: str, connection_id: str) -> None:
        import os
        if os.getenv("ENABLE_BOTS", "false").lower() != "true":
            logger.info("[SendMessageNode] [sim] WA → %s: %s", to, message[:80])
            return

        try:
            from state import wa_session
            ok = await wa_session.send_message(connection_id, to, message)
            if not ok:
                logger.warning("[SendMessageNode] WA → %s: send_message retornó False", to)
            else:
                logger.info("[SendMessageNode] WA → %s enviado", to)
        except Exception as e:
            logger.error("[SendMessageNode] Error WA → %s: %s", to, e)

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "to": {
                "type":    "string",
                "label":   "Destinatario (vacío = usuario de la conversación)",
                "default": "",
            },
            "message": {
                "type":     "string",
                "label":    "Mensaje (soporta {{placeholders}})",
                "default":  "",
                "required": True,
            },
            "channel": {
                "type":    "select",
                "label":   "Canal",
                "default": "auto",
                "options": ["auto", "telegram", "whatsapp"],
            },
        }
