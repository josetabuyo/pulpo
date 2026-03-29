"""
Node: notify_worker

Notifica a un trabajador que hay un pedido de servicio.
Canales intentados en orden: Telegram, WhatsApp.

En modo simulador (ENABLE_BOTS=false) o si no hay cliente activo, loguea el mensaje.
"""
import logging
import os

logger = logging.getLogger(__name__)


async def notify(worker: dict, mensaje_vecino: str, empresa_id: str) -> bool:
    """
    Envía una notificación al trabajador.
    Retorna True si el mensaje fue enviado, False si solo fue logueado.
    """
    nombre = worker.get("nombre", "trabajador")
    oficio = worker.get("oficio", "servicio")

    texto = (
        f"🔔 *Nuevo pedido de {oficio}*\n\n"
        f"Un vecino de Villa Lugano necesita ayuda:\n\n"
        f"_{mensaje_vecino}_\n\n"
        f"¿Podés tomar este trabajo? Respondé a este mensaje para confirmar."
    )

    # Intentar Telegram primero
    telegram_id = worker.get("telegram_id")
    if telegram_id:
        sent = await _send_telegram(telegram_id, texto, empresa_id)
        if sent:
            logger.info("[notify_worker] Mensaje enviado por Telegram a %s (%s)", nombre, telegram_id)
            return True

    # Fallback: loguear (WhatsApp queda para implementación futura)
    whatsapp = worker.get("whatsapp")
    if whatsapp:
        logger.info(
            "[notify_worker] [PENDIENTE WA] Notificar a %s (%s): %s",
            nombre, whatsapp, texto[:80],
        )
    else:
        logger.info("[notify_worker] Sin canal disponible para %s — mensaje logueado", nombre)

    return False


async def _send_telegram(telegram_id: str, texto: str, empresa_id: str) -> bool:
    if os.getenv("ENABLE_BOTS", "false").lower() != "true":
        logger.info("[notify_worker] Modo simulador — mensaje Telegram NO enviado (logueado)")
        return False

    try:
        from state import clients
        tg_session = next(
            (k for k, v in clients.items()
             if v.get("bot_id") == empresa_id and v.get("type") == "telegram" and v.get("client")),
            None,
        )
        if not tg_session:
            logger.warning("[notify_worker] Sin bot Telegram activo para empresa '%s'", empresa_id)
            return False

        tg_app = clients[tg_session]["client"]
        await tg_app.bot.send_message(
            chat_id=int(telegram_id),
            text=texto,
            parse_mode="Markdown",
        )
        return True
    except Exception as e:
        logger.error("[notify_worker] Error enviando Telegram a %s: %s", telegram_id, e)
        return False
