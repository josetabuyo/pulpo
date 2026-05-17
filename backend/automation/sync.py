"""
delta_sync — proceso unificado de recolección de mensajes desde WA Web.

Reemplaza los 4 caminos de recolección anteriores:
  - on_message (polling real-time)
  - sync_contact / sync_all_contacts (lectura desde DB)
  - scrape_full_history_v2 + _do_import
  - full_resync_contact

Un único entry point, parametrizado por StopCondition.
"""
from enum import Enum
from datetime import datetime
from typing import Callable
import unicodedata
import logging

from graphs.nodes.summarize import (
    accumulate,
    clear_contact,
    _newest_message_ts,
)

logger = logging.getLogger(__name__)


class StopCondition(Enum):
    FULL_OVERWRITE = "full_overwrite"   # borra y reescribe desde cero
    FULL_ENRICH    = "full_enrich"      # re-parsea sin borrar, enriquece faltantes
    UNTIL_KNOWN    = "until_known"      # para ante el primer mensaje ya conocido


async def delta_sync(
    wa_session,
    session_id: str,
    contact_name: str,
    empresa_id: str,
    contact_phone: str,
    stop_condition: StopCondition,
    since_date: datetime | None = None,
    owner_name: str | None = None,
    on_progress: Callable | None = None,
    doc_save_dir=None,
    skip_audio_ts: set | None = None,
    max_scroll_rounds: int = 500,
    scroll_step: int = 300,
) -> dict:
    """
    Recolecta mensajes del chat de un contacto en WA Web y los acumula en .md.

    Parámetros:
        wa_session      — instancia WhatsAppSession con scrape_full_history_v2
        session_id      — número de teléfono del bot (key en clients dict)
        contact_name    — nombre del contacto en WA Web (para búsqueda en sidebar)
        empresa_id      — id de la empresa (para accumulate y rutas de archivos)
        contact_phone   — identificador del contacto (slug o número)
        stop_condition  — FULL_OVERWRITE: borra antes; FULL_ENRICH: no borra;
                          UNTIL_KNOWN: para ante el primer mensaje ya guardado
        since_date      — para FULL_OVERWRITE/ENRICH: límite inferior del scrape
        owner_name      — nombre WA del dueño del teléfono (sender de salientes)
        on_progress     — callback(round_n, new_in_round, total) para progreso

    Retorna:
        {"scraped": N, "new": M, "stop_reason": str}
    """
    # ── Determinar punto de corte ────────────────────────────────────────────
    stop_before_ts = None
    if stop_condition == StopCondition.UNTIL_KNOWN:
        stop_before_ts = _newest_message_ts(empresa_id, contact_phone)
    else:
        stop_before_ts = since_date  # None = ir hasta el tope

    # ── FULL_OVERWRITE: limpiar antes de scrapear ────────────────────────────
    if stop_condition == StopCondition.FULL_OVERWRITE:
        clear_contact(empresa_id, contact_phone)

    # ── Scrape ───────────────────────────────────────────────────────────────
    scrape_kwargs: dict = dict(
        stop_before_ts=stop_before_ts,
        on_progress=on_progress,
        max_scroll_rounds=max_scroll_rounds,
        scroll_step=scroll_step,
    )
    if doc_save_dir is not None:
        scrape_kwargs["doc_save_dir"] = doc_save_dir
    if skip_audio_ts is not None:
        scrape_kwargs["skip_audio_ts"] = skip_audio_ts

    messages = await wa_session.scrape_full_history_v2(
        session_id,
        contact_name,
        **scrape_kwargs,
    )

    from db import log_message_historic

    # ── Acumular ─────────────────────────────────────────────────────────────
    saved = 0
    for msg in messages:
        body = msg.get("body", "")
        if not body.strip():
            continue

        # Descartar reacciones emoji (body ≤ 2 chars de categoría símbolo)
        bare = body.strip()
        if len(bare) <= 2 and all(
            unicodedata.category(c) in ('So', 'Sm', 'Sk', 'Sc', 'Po', 'Ps', 'Pe')
            for c in bare if c.strip()
        ):
            continue

        ts_str = msg.get("timestamp", "")
        ts = None
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

        # Guardar en DB (dedup por contact+body+minuto — idempotente)
        if ts_str:
            outbound = 1 if msg.get("is_outbound") else 0
            await log_message_historic(
                empresa_id, session_id, contact_name, contact_name,
                body, ts_str, outbound,
            )

        sender = _resolve_sender(msg, contact_name, owner_name)
        content = f"{sender}: {body}"

        quoted = msg.get("quoted", "")
        if quoted:
            quoted_sender = msg.get("quotedSender", "")
            reply_prefix = f"[{quoted_sender}] " if quoted_sender else ""
            content = f"{content}\n> ↩ {reply_prefix}{quoted}"

        accumulate(
            empresa_id=empresa_id,
            contact_phone=contact_phone,
            contact_name=contact_name,
            msg_type=msg.get("msg_type", "text"),
            content=content.strip(),
            timestamp=ts,
        )
        saved += 1

    logger.info(
        "[delta_sync] %s/%s — scraped=%d new=%d stop=%s",
        empresa_id, contact_phone, len(messages), saved, stop_condition.value,
    )

    return {
        "scraped": len(messages),
        "new": saved,
        "stop_reason": stop_condition.value,
    }


def _resolve_sender(msg: dict, contact_name: str, owner_name: str | None) -> str:
    """
    Determina el sender canónico de un mensaje.
    Saliente: sender del scraper > owner_name > "Tú"
    Entrante: sender del scraper > contact_name
    """
    if msg.get("is_outbound"):
        return msg.get("sender") or owner_name or "Tú"
    return msg.get("sender") or contact_name
