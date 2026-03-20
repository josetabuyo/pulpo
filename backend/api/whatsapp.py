"""
Endpoints de WhatsApp.

Flujo de "Vincular QR":
  1. POST /connect/{number}  → abre sesión, intenta restaurar auth
     - Si retorna status="restored": ya está listo, no hay QR
     - Si retorna status="connecting": hay que pedir QR y esperar scan
  2. GET  /qr/{session_id}   → devuelve el QR como base64 (polling)
  3. GET  /status/{session_id} → estado actual de la sesión
"""
import base64

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks

from api.deps import require_admin, require_client
from config import load_config
from state import clients, wa_session

router = APIRouter()


@router.post("/connect/{number}", dependencies=[Depends(require_client)])
async def connect_phone(number: str, background_tasks: BackgroundTasks):
    config = load_config()
    found = None
    for bot in config.get("bots", []):
        if any(p["number"] == number for p in bot.get("phones", [])):
            found = {"bot_id": bot["id"], "number": number}
            break

    if not found:
        raise HTTPException(status_code=404, detail="Número no encontrado.")

    session_id = number
    existing = clients.get(session_id, {})

    # Si ya está conectado o en proceso, no relanzar
    if existing.get("status") in ("connecting", "qr_needed", "qr_ready", "ready"):
        return {"ok": True, "status": existing["status"], "sessionId": session_id}

    # Lanzar conexión en background (puede tardar varios segundos)
    background_tasks.add_task(_connect_and_get_qr, session_id, found["bot_id"])
    return {"ok": True, "status": "connecting", "sessionId": session_id}


@router.get("/qr/{session_id}", dependencies=[Depends(require_client)])
async def get_qr(session_id: str):
    state = clients.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Sesión no iniciada. Llamá primero a /connect.")
    if state["status"] == "ready":
        return {"status": "ready"}
    if state.get("qr"):
        return {"status": state["status"], "qr": state["qr"]}
    return {"status": state["status"]}


@router.get("/status/{session_id}", dependencies=[Depends(require_client)])
async def get_status(session_id: str):
    state = clients.get(session_id)
    if not state:
        return {"status": "unknown"}
    alive = await wa_session.is_page_alive(session_id)
    return {"status": state["status"], "alive": alive}


@router.post("/disconnect/{session_id}", dependencies=[Depends(require_admin)])
async def disconnect_session(session_id: str):
    """Cierra el contexto Chromium de una sesión WA limpiamente (sin kill)."""
    await wa_session.close_session(session_id)
    if session_id in clients:
        clients[session_id]["status"] = "disconnected"
        clients[session_id]["qr"] = None
    return {"ok": True, "session_id": session_id}


@router.post("/disconnect-all", dependencies=[Depends(require_admin)])
async def disconnect_all():
    """Cierra todos los contextos Chromium de la app sin tocar el browser del MCP."""
    closed = []
    for session_id, state in list(clients.items()):
        if state.get("type") != "whatsapp":
            continue
        await wa_session.close_session(session_id)
        clients[session_id]["status"] = "disconnected"
        clients[session_id]["qr"] = None
        closed.append(session_id)
    return {"ok": True, "closed": closed}


@router.get("/dom-inspect/{session_id}", dependencies=[Depends(require_admin)])
async def dom_inspect(session_id: str, chat: str = ""):
    """Debug: inspecciona selectores de mensajes. Si ?chat=Nombre abre ese chat primero."""
    page = wa_session.get_page(session_id)
    if not page or page.is_closed():
        raise HTTPException(status_code=404, detail="Sesión no activa.")

    if chat:
        import unicodedata
        def _norm(s):
            return unicodedata.normalize("NFKC", s).strip()
        row_handle = await page.evaluate_handle(
            """(target) => {
                const norm = s => s.replace(/[\\u00a0\\u202a\\u202c\\u200e\\u200f]/g,' ').trim();
                const grid = document.querySelector('[role="grid"]');
                if (!grid) return null;
                for (const s of grid.querySelectorAll('span[title]')) {
                    if (norm(s.getAttribute('title')) === norm(target)) {
                        return s.closest('[role="row"]') || s.closest('[data-id]') || s;
                    }
                }
                return null;
            }""",
            _norm(chat),
        )
        if row_handle and not await row_handle.evaluate("el => el === null"):
            await row_handle.scroll_into_view_if_needed()
            await row_handle.click()
        await page.wait_for_timeout(3000)

    # Listar todos los títulos en el sidebar para debug
    result = await page.evaluate("""
    () => {
        const prePlain   = document.querySelectorAll('[data-pre-plain-text]').length;
        const msgBoxes   = document.querySelectorAll('[data-testid="msg-container"]').length;
        const copyable   = document.querySelectorAll('span.copyable-text').length;
        // Todos los títulos en el sidebar
        const titles = [...document.querySelectorAll('[role="grid"] span[title]')]
                         .map(s => s.getAttribute('title')).filter(Boolean).slice(0, 30);
        // Primer msg-container HTML
        const box = document.querySelector('[data-testid="msg-container"]');
        const boxHtml = box ? box.outerHTML.slice(0, 600) : null;
        // Primer data-pre-plain-text
        const el = document.querySelector('[data-pre-plain-text]');
        const sample = el ? { tag: el.tagName, val: el.getAttribute('data-pre-plain-text') } : null;
        return { prePlain, msgBoxes, copyable, titles, sample, boxHtml };
    }
    """)
    return result


@router.get("/screenshot/{session_id}", dependencies=[Depends(require_admin)])
async def get_screenshot(session_id: str):
    """Captura un screenshot del browser headless para esa sesión de WA."""
    page = wa_session.get_page(session_id)
    if not page or page.is_closed():
        raise HTTPException(status_code=404, detail="Sesión no activa.")
    try:
        screenshot_bytes = await page.screenshot(type="png", full_page=False)
        b64 = base64.b64encode(screenshot_bytes).decode()
        return {"screenshot": f"data:image/png;base64,{b64}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/full-sync", dependencies=[Depends(require_admin)])
async def full_sync(background_tasks: BackgroundTasks):
    """
    Scrapea el historial completo de todos los contactos/grupos WA registrados
    y guarda los mensajes históricos en la DB (idempotente — no duplica).
    Corre en background; retorna inmediatamente.
    """
    background_tasks.add_task(_run_full_sync)
    return {"ok": True, "message": "Full sync iniciado en background"}


async def _run_full_sync() -> None:
    import logging
    from db import log_message_historic, get_contacts
    from config import get_empresas_for_bot

    _log = logging.getLogger(__name__)
    _log.info("[full-sync] Iniciando sync completo de historial WA...")
    total = 0

    for session_id, state in list(clients.items()):
        if state.get("type") != "whatsapp":
            continue
        if state.get("status") != "ready":
            _log.info(f"[full-sync] Sesión {session_id} no está lista, saltando.")
            continue

        bot_phone = session_id
        empresa_ids = get_empresas_for_bot(bot_phone)
        if not empresa_ids:
            empresa_ids = [state.get("bot_id", "")]

        # Recopilar contactos WA únicos de todas las empresas de este bot
        seen_contact_names: set[str] = set()
        contacts_to_sync: list[dict] = []
        for eid in empresa_ids:
            for contact in await get_contacts(eid):
                if contact["name"] not in seen_contact_names:
                    wa_chs = [ch for ch in contact.get("channels", []) if ch["type"] == "whatsapp"]
                    if wa_chs:
                        seen_contact_names.add(contact["name"])
                        contacts_to_sync.append({"contact": contact, "empresa_ids": empresa_ids})

        for item in contacts_to_sync:
            contact = item["contact"]
            eids = item["empresa_ids"]
            contact_name = contact["name"]
            wa_channels = [ch for ch in contact.get("channels", []) if ch["type"] == "whatsapp"]

            _log.info(f"[full-sync] Scraping '{contact_name}'...")
            messages = await wa_session.scrape_full_history(session_id, contact_name)

            for msg in messages:
                for ch in wa_channels:
                    phone = ch["value"]
                    is_group = ch.get("is_group", False)

                    # Para grupos: guardar "Sender: body" si hay sender
                    if is_group and msg.get("sender"):
                        body = f"{msg['sender']}: {msg['body']}"
                    else:
                        body = msg["body"]

                    outbound = 1 if msg.get("is_outbound") else 0

                    for eid in eids:
                        saved = await log_message_historic(
                            eid, bot_phone, phone, contact_name,
                            body, msg["timestamp"], outbound,
                        )
                        if saved:
                            total += 1

    _log.info(f"[full-sync] Completado. {total} mensajes nuevos importados.")


@router.post("/refresh", dependencies=[Depends(require_admin)])
async def refresh():
    reconnected = 0
    for session_id, state in clients.items():
        if state.get("type") != "whatsapp":
            continue
        if not await wa_session.is_page_alive(session_id):
            bot_id = state.get("bot_id", "")
            result = await wa_session.connect(session_id, bot_id)
            if result in ("restored", "qr_needed"):
                reconnected += 1
    return {"ok": True, "reconnected": reconnected}


# ------------------------------------------------------------------
# Tarea background: conectar y capturar QR si hace falta
# ------------------------------------------------------------------

def _get_wa_config(config: dict, number: str) -> dict:
    """Extrae bot_id para un número dado."""
    for bot in config.get("bots", []):
        for phone_cfg in bot.get("phones", []):
            if phone_cfg.get("number") == number:
                return {"bot_id": bot["id"]}
    return {"bot_id": ""}


async def _connect_and_get_qr(session_id: str, bot_id: str) -> None:
    result = await wa_session.connect(session_id, bot_id)

    if result == "restored":
        # Sesión restaurada — arrancar listener directamente
        cfg = _get_wa_config(load_config(), session_id)
        await wa_session.start_listening(session_id, cfg["bot_id"], session_id)
        return

    if result == "qr_needed":
        qr = await wa_session.get_qr(session_id)
        if qr:
            authenticated = await wa_session.wait_for_auth(session_id)
            if authenticated:
                cfg = _get_wa_config(load_config(), session_id)
                await wa_session.start_listening(session_id, cfg["bot_id"], session_id)
