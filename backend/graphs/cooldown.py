"""
FlowCooldown — rate limit de replies por (flow, contacto).

Evita que un flow le responda al mismo contacto más seguido que el
cooldown_hours configurado en su trigger.
"""
import logging
import time

from .nodes import NODE_REGISTRY

logger = logging.getLogger(__name__)


def cooldown_hours(trigger_config: dict, trigger_type: str) -> float:
    """
    Lee cooldown_hours del config del trigger.
    Si la clave no está (flow creado antes de que existiera el campo),
    usa el default del schema del nodo en lugar de 0.
    Esto evita que flows viejos queden sin cooldown silenciosamente.
    """
    val = trigger_config.get("cooldown_hours")
    if val is None:
        node_cls = NODE_REGISTRY.get(trigger_type)
        if node_cls and hasattr(node_cls, "config_schema"):
            val = node_cls.config_schema().get("cooldown_hours", {}).get("default", 0)
        else:
            val = 0
    return float(val or 0)


class FlowCooldown:
    """
    Registro en memoria del último reply enviado por (flow_id, contact_phone).

    Vive en memoria de proceso: se resetea al reiniciar el backend (aceptado —
    el costo de un reply de más tras un restart es bajo). No necesita locks:
    el backend corre en un solo event loop y no hay awaits entre la lectura
    y la escritura del dict.
    """

    def __init__(self) -> None:
        self._last_reply: dict[tuple[str, str], float] = {}

    def is_active(self, flow_id: str, contact: str, hours: float) -> bool:
        """True si el cooldown sigue vigente (todavía no pasaron `hours` horas)."""
        if hours <= 0:
            return False
        last = self._last_reply.get((str(flow_id), contact))
        if last is None:
            return False
        elapsed_h = (time.time() - last) / 3600
        if elapsed_h < hours:
            logger.debug(
                "[cooldown] activo para flow '%s' / contacto '%s' — restan %.1fh",
                flow_id, contact, hours - elapsed_h,
            )
            return True
        return False

    def mark(self, flow_id: str, contact: str, when: float | None = None) -> None:
        """Registra un reply enviado. `when` permite backdatear (solo tests)."""
        self._last_reply[(str(flow_id), contact)] = time.time() if when is None else when

    def has(self, flow_id: str, contact: str) -> bool:
        return (str(flow_id), contact) in self._last_reply

    def pop(self, flow_id: str, contact: str) -> None:
        self._last_reply.pop((str(flow_id), contact), None)

    def clear(self) -> None:
        self._last_reply.clear()


# Instancia única del proceso — compartida por engine y tests.
flow_cooldown = FlowCooldown()
