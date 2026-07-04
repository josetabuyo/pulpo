"""
MetricNode — registra una métrica de negocio y, opcionalmente, notifica a un
sistema externo interesado vía webhook.

Guardar la métrica es el paso crítico. El webhook es un side-effect
best-effort dirigido a un sistema externo (ej: uno que integra Pulpo y quiere
enterarse en tiempo real de qué piden los usuarios): si falla, NO aborta el
flow — pero el fallo queda logueado a nivel ERROR para poder detectarlo.
"""
import json
import logging

from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)


class MetricNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        metric_name = interpolate(self.config.get("metric_name", ""), state).strip()
        if not metric_name:
            logger.warning("[MetricNode] metric_name vacío — no se registra nada")
            return state

        value = interpolate(str(self.config.get("value", "")), state)

        raw_metadata = self.config.get("metadata") or {}
        metadata = {k: interpolate(str(v), state) for k, v in raw_metadata.items()} if isinstance(raw_metadata, dict) else {}

        from pulpo.core import db
        await db.insert_metric(
            bot_id=state.bot_id or "",
            contact_phone=state.contact_phone or "",
            contact_name=state.contact_name or "",
            canal=state.canal or "",
            metric_name=metric_name,
            value=value,
            metadata=json.dumps(metadata, default=str) if metadata else None,
        )
        logger.info("[MetricNode] %s=%s (bot=%s, contact=%s)", metric_name, value, state.bot_id, state.contact_phone)

        webhook_url = (self.config.get("webhook_url") or "").strip()
        if webhook_url:
            await self._notify_webhook(webhook_url, {
                "metric_name":   metric_name,
                "value":         value,
                "bot_id":        state.bot_id,
                "contact_phone": state.contact_phone,
                "contact_name":  state.contact_name,
                "canal":         state.canal,
                "metadata":      metadata,
            })

        return state

    @staticmethod
    async def _notify_webhook(url: str, payload: dict) -> None:
        """Fire-and-forget: un fallo no interrumpe el flow, pero queda en el log
        (nivel ERROR) para poder detectarlo. No hay reintentos."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.error("[MetricNode] webhook falló url=%s metric=%s: %s", url, payload.get("metric_name"), e)

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "metric_name": {
                "type":     "string",
                "label":    "Nombre de la métrica",
                "default":  "",
                "hint":     "Ej: intencion_detectada, producto_consultado. Soporta {{templates}}",
                "required": True,
            },
            "value": {
                "type":     "string",
                "label":    "Valor",
                "default":  "",
                "hint":     "Soporta {{templates}}, ej: {{message}} o {{route}}",
                "required": True,
            },
            "metadata": {
                "type":    "json",
                "label":   "Metadata extra (opcional)",
                "default": {},
                "hint":    '{"campo": "{{template}}"}',
            },
            "webhook_url": {
                "type":    "string",
                "label":   "Webhook (opcional)",
                "default": "",
                "hint":    "POST con {metric_name, value, bot_id, contact_phone, contact_name, canal, metadata}. "
                           "Fire-and-forget: si falla no interrumpe el flow, el error queda logueado.",
            },
        }
