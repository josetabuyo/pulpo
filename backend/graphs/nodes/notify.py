"""
NotifyNode — envía notificaciones y genera reply para el usuario.

Config:
  type:    str — "worker" (notifica al trabajador vía Telegram/WA)
  channel: str — "telegram" (por ahora el único soportado)
"""
import json
import logging
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


class NotifyNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        notify_type = self.config.get("type", "worker")

        if notify_type == "worker":
            await self._notify_worker(state)
        else:
            logger.warning("[NotifyNode] type desconocido: %s", notify_type)

        return state

    async def _notify_worker(self, state: FlowState) -> None:
        """
        Lee state.context (JSON de SearchNode), notifica al trabajador,
        registra el pedido en la DB y genera el reply para el usuario.
        """
        try:
            data   = json.loads(state.context) if state.context else {}
        except (json.JSONDecodeError, TypeError):
            data   = {}

        oficio     = data.get("oficio", "otro")
        worker     = data.get("worker")
        empresa_id = state.empresa_id

        # Notificar al trabajador
        if worker:
            try:
                from nodes import notify_worker as notify_worker_mod
                await notify_worker_mod.notify(worker, state.message, empresa_id)
            except Exception as e:
                logger.error("[NotifyNode] Error notificando worker: %s", e)

        # Registrar el pedido en la DB
        try:
            from db import create_job
            await create_job(
                empresa_id=empresa_id,
                cliente_phone=state.contact_phone or "",
                canal=state.canal or "telegram",
                oficio=oficio,
                trabajador_id=(worker.get("telegram_id") or worker.get("whatsapp")) if worker else None,
                trabajador_nombre=worker["nombre"] if worker else None,
            )
        except Exception as e:
            logger.error("[NotifyNode] Error registrando job: %s", e)

        # Generar reply
        if worker:
            nombre = worker["nombre"]
            reply = (
                f"¡Encontramos a alguien! *{nombre}* puede ayudarte con tu pedido de {oficio} 🙌\n"
                f"Te va a contactar pronto."
            )
            if worker.get("whatsapp"):
                reply += f"\n📞 También podés contactarlo directo: {worker['whatsapp']}"
        else:
            oficio_display = oficio if oficio != "otro" else "profesional"
            reply = (
                f"Estamos buscando un {oficio_display} para vos 🔍\n"
                f"Te avisamos cuando tengamos novedades."
            )

        state.reply = reply
        logger.info("[NotifyNode] reply generado para oficio='%s' worker=%s",
                    oficio, worker["nombre"] if worker else None)

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type":    {"type": "select", "label": "Tipo de notificación", "default": "worker",
                        "options": ["worker"]},
            "channel": {"type": "select", "label": "Canal",                "default": "telegram",
                        "options": ["telegram"]},
        }
