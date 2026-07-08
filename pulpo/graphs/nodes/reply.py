"""
SendMessageNode — único nodo que envía mensajes.

Si `to` está vacío → escribe en state.data["reply"] (el adapter lo envía al usuario).
Si `to` tiene valor → envía inmediatamente al destinatario via Telegram.

Config:
  to:            str   — destinatario. Vacío = reply al usuario de la conversación.
                         Soporta placeholders: "{{telegram}}", "{{contact_phone}}", etc.
  message:       str   — texto con placeholders.
  channel:       str   — "telegram" (default: "telegram")
  max_age_hours: float — edad máxima del mensaje original para responder (solo reply al usuario).
                         0 = sin límite. Default: 1.
                         Previene respuestas automáticas a mensajes retroactivos.
"""
import logging
from datetime import datetime
from ..conversation import record_bot_reply
from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)


class SendMessageNode(BaseNode):
    label = "Enviar mensaje"
    color = "#15803d"
    description = "Envía un mensaje al usuario o a un contacto externo vía Telegram."

    async def run(self, state: FlowState) -> FlowState:
        if state.from_delta_sync:
            return state

        to      = interpolate(self.config.get("to", ""), state).strip()
        message = interpolate(self.config.get("message", ""), state)
        channel = interpolate(self.config.get("channel", "telegram"), state).strip() or "telegram"

        if not to:
            # Validar antigüedad del mensaje original antes de responder al usuario
            max_age = float(self.config.get("max_age_hours", 1.0))
            if max_age > 0 and state.timestamp is not None:
                now = datetime.now()
                msg_ts = state.timestamp.replace(tzinfo=None) if state.timestamp.tzinfo else state.timestamp
                age_hours = (now - msg_ts).total_seconds() / 3600
                if age_hours > max_age:
                    logger.warning(
                        "[SendMessageNode] Mensaje de %s tiene %.1fh de antigüedad (límite %.1fh) — reply bloqueado.",
                        state.contact_phone, age_hours, max_age,
                    )
                    return state
            state.data["reply"] = message
            # Solo el reply al usuario (no los envíos a terceros) forma parte
            # de la conversación con él — y solo si esta ejecución ya es una
            # conversación (ver graphs/conversation.py).
            record_bot_reply(state, message)
            return state

        await self._send(to, message, channel, state)
        return state

    async def _send(self, to: str, message: str, channel: str, state: FlowState) -> None:
        if channel == "telegram":
            await self._send_telegram(to, message, state.bot_id)
        elif channel == "teli":
            await self._send_teli(to, message)
        else:
            logger.warning("[SendMessageNode] canal desconocido: %s", channel)

    async def _send_telegram(self, chat_id: str, message: str, bot_id: str) -> None:
        import os
        if os.getenv("ENABLE_BOTS", "false").lower() != "true":
            logger.info("[SendMessageNode] [sim] TG → %s: %s", chat_id, message[:80])
            return

        from pulpo.core.state import clients
        tg_session = next(
            (k for k, v in clients.items()
             if v.get("connection_id") == bot_id
             and v.get("type") == "telegram"
             and v.get("client")),
            None,
        )
        if not tg_session:
            logger.warning("[SendMessageNode] Sin bot Telegram activo para bot '%s'", bot_id)
            return

        bot = clients[tg_session]["client"].bot
        try:
            await bot.send_message(chat_id=int(chat_id), text=message, parse_mode="Markdown")
            logger.info("[SendMessageNode] TG → %s enviado", chat_id)
        except Exception:
            try:
                await bot.send_message(chat_id=int(chat_id), text=message)
                logger.info("[SendMessageNode] TG → %s enviado (plain text)", chat_id)
            except Exception as e:
                logger.error("[SendMessageNode] Error TG → %s: %s", chat_id, e)

    async def _send_teli(self, to: str, message: str) -> None:
        import os
        if os.getenv("ENABLE_BOTS", "false").lower() != "true":
            logger.info("[SendMessageNode] [sim] teli → %s: %s", to, message[:80])
            return
        from pathlib import Path
        from telethon import TelegramClient
        SESSION  = str(Path("/Users/josetabuyo/Development/teli/data/sessions/user_me"))
        API_ID   = 31604778
        API_HASH = "385bf75876904b022cb411c1c1954088"
        client = TelegramClient(SESSION, API_ID, API_HASH)
        try:
            await client.start()
            await client.send_message(int(to), message)
            logger.info("[SendMessageNode] teli → %s enviado", to)
        except Exception as e:
            logger.error("[SendMessageNode] Error teli → %s: %s", to, e)
        finally:
            await client.disconnect()

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "to": {
                "type":    "string",
                "label":   "Destinatario",
                "default": "",
                "hint":    "Vacío = reply al usuario de la conversación. Soporta {{placeholders}}",
            },
            "message": {
                "type":     "textarea",
                "label":    "Mensaje",
                "default":  "",
                "required": True,
                "rows":     5,
                "hint":     "Soporta {{placeholders}} como {{nombre}}",
            },
            "channel": {
                "type":    "select",
                "label":   "Canal",
                "default": "telegram",
                "options": ["telegram", "teli"],
            },
            "max_age_hours": {
                "type":    "float",
                "label":   "Edad máxima para responder (horas)",
                "default": 1.0,
                "hint":    "Solo aplica al reply al usuario (destinatario vacío). 0 = sin límite.",
            },
        }
