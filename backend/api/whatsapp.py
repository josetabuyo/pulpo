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
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel

from api.deps import require_admin, require_client
from config import load_config
from state import clients, wa_session

router = APIRouter()


@router.post("/connect/{number}", dependencies=[Depends(require_client)])
async def connect_phone(number: str, background_tasks: BackgroundTasks):
    config = load_config()
    found = None
    for empresa in config.get("empresas", []):
        if any(p["number"] == number for p in empresa.get("phones", [])):
            found = {"connection_id": empresa["id"], "number": number}
            break

    if not found:
        raise HTTPException(status_code=404, detail="Número no encontrado.")

    session_id = number
    existing = clients.get(session_id, {})

    # Si ya está conectado o en proceso, no relanzar
    if existing.get("status") in ("connecting", "qr_needed", "qr_ready", "ready"):
        return {"ok": True, "status": existing["status"], "sessionId": session_id}

    # Lanzar conexión en background (puede tardar varios segundos)
    background_tasks.add_task(_connect_and_get_qr, session_id, found["connection_id"])
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

    result = await page.evaluate("""
    () => {
        const prePlain   = document.querySelectorAll('[data-pre-plain-text]').length;
        const msgBoxes   = document.querySelectorAll('[data-testid="msg-container"]').length;
        const copyable   = document.querySelectorAll('span.copyable-text').length;
        const audioEls   = document.querySelectorAll('audio, [data-testid="audio-play"]').length;
        // Primer data-pre-plain-text
        const el = document.querySelector('[data-pre-plain-text]');
        const sample = el ? { tag: el.tagName, val: el.getAttribute('data-pre-plain-text') } : null;
        // HTML del primer mensaje con audio (para ver estructura)
        const audioMsg = document.querySelector('[data-testid="audio-play"]');
        const audioHtml = audioMsg ? audioMsg.closest('[class*="message"]')?.outerHTML?.slice(0, 800) : null;
        // Primer data-pre-plain-text que NO tiene span.copyable-text (posibles audios)
        const withoutText = [...document.querySelectorAll('[data-pre-plain-text]')]
            .filter(e => !e.querySelector('span.copyable-text'));
        const noTextSample = withoutText[0] ? withoutText[0].outerHTML.slice(0, 600) : null;
        return { prePlain, msgBoxes, copyable, audioEls, sample, audioHtml, noTextSample };
    }
    """)
    return result


@router.get("/audio-probe/{session_id}", dependencies=[Depends(require_admin)])
async def audio_probe(session_id: str):
    """
    Inspección profunda: recolecta todos los data-icon y data-testid del DOM
    para descubrir los selectores reales de audios/voz en WA Web.
    """
    page = wa_session.get_page(session_id)
    if not page or page.is_closed():
        raise HTTPException(status_code=404, detail="Sesión no activa.")

    result = await page.evaluate("""
    () => {
        // 1. Todos los data-icon únicos
        const icons = {};
        for (const el of document.querySelectorAll('[data-icon]')) {
            const v = el.getAttribute('data-icon');
            icons[v] = (icons[v] || 0) + 1;
        }

        // 2. Todos los data-testid únicos (filtrar audio-related)
        const testids = {};
        for (const el of document.querySelectorAll('[data-testid]')) {
            const v = el.getAttribute('data-testid');
            if (v.includes('audio') || v.includes('ptt') || v.includes('voice')
                || v.includes('play') || v.includes('msg')) {
                testids[v] = (testids[v] || 0) + 1;
            }
        }

        // 3. Elementos audio
        const audioEls = document.querySelectorAll('audio');
        const audioInfo = [...audioEls].slice(0, 5).map(a => ({
            src: a.src ? a.src.slice(0, 100) : '(vacío)',
            duration: a.duration,
            outerHtml: a.outerHTML.slice(0, 300),
        }));

        // 4. HTML de un mensaje sin span.copyable-text (probable audio/voz)
        const noText = [...document.querySelectorAll('[data-pre-plain-text]')]
            .filter(e => !e.querySelector('span.copyable-text'));
        const noTextSamples = noText.slice(0, 3).map(e => e.outerHTML.slice(0, 600));

        // 5. Buscar por aria-label que contenga play/reproducir/audio/voice
        const ariaPlayEls = [...document.querySelectorAll('[aria-label]')]
            .filter(e => /play|reproducir|audio|voice|ptt|voz/i.test(e.getAttribute('aria-label')));
        const ariaLabels = ariaPlayEls.slice(0, 10).map(e => ({
            tag: e.tagName,
            ariaLabel: e.getAttribute('aria-label'),
            dataIcon: e.getAttribute('data-icon'),
            dataTestid: e.getAttribute('data-testid'),
            outerHtml: e.outerHTML.slice(0, 200),
        }));

        // 6. Análisis profundo de mensajes de voz (ptt-status)
        const pttEls = document.querySelectorAll('[data-icon="ptt-status"]');
        const pttContainers = [];
        for (const el of pttEls) {
            let container = el;
            for (let i = 0; i < 20; i++) {
                if (!container.parentElement) break;
                container = container.parentElement;
                if (container.dataset.id || container.getAttribute('role') === 'row'
                    || container.classList.contains('message-in')
                    || container.classList.contains('message-out')) break;
            }
            const meta = container.querySelector('[data-testid="msg-meta"]');
            const metaAria = meta ? meta.getAttribute('aria-label') : null;
            const metaText = meta ? meta.innerText.trim() : null;

            // Buscar tiempo con regex en todos los spans/divs del contenedor
            let timeFromText = null;
            for (const span of container.querySelectorAll('span, div')) {
                const t = span.innerText ? span.innerText.trim() : '';
                if (/^\d{1,2}:\d{2}(\s*(a|p)\.\s*m\.?)?$/.test(t)) {
                    timeFromText = t;
                    break;
                }
            }

            // Sender: span[aria-label="Name:"] o [data-testid="author"]
            const senderAriaEl = container.querySelector('span[aria-label$=":"]');
            const senderTestidEl = container.querySelector('[data-testid="author"]');
            const senderAriaLabel = senderAriaEl ? senderAriaEl.getAttribute('aria-label') : null;
            const senderTestid = senderTestidEl ? senderTestidEl.innerText : null;

            // Buscar data-pre-plain-text en ancestros (a veces está en padre del padre)
            let prePlain = null;
            let anc = container;
            for (let i = 0; i < 5; i++) {
                if (!anc) break;
                const pp = anc.querySelector('[data-pre-plain-text]');
                if (pp) { prePlain = pp.getAttribute('data-pre-plain-text'); break; }
                anc = anc.parentElement;
            }

            // Buscar TODOS los aria-label en el contenedor completo
            const allAriaLabels = [...container.querySelectorAll('[aria-label]')]
                .map(e => ({ tag: e.tagName, aria: e.getAttribute('aria-label'), text: e.innerText?.trim()?.slice(0,40) }));

            // Buscar TODO el texto visible en el contenedor (para encontrar timestamp)
            const allTextNodes = [];
            const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
            let node;
            while (node = walker.nextNode()) {
                const t = node.textContent.trim();
                if (t && t.length > 0 && t.length < 100) allTextNodes.push(t);
            }

            // Buscar span con text que parece hora (ej: "9:41 a. m." o "21:41")
            const timeSpans = [...container.querySelectorAll('span, div')]
                .map(e => e.innerText?.trim())
                .filter(t => t && /^\d{1,2}:\d{2}/.test(t));

            // Buscar el div/span que tiene el data-pre-plain-text en el PARENT del container
            let parentPrePlain = null;
            let p = container.parentElement;
            for (let i = 0; i < 10; i++) {
                if (!p) break;
                const pp = p.getAttribute('data-pre-plain-text');
                if (pp) { parentPrePlain = pp; break; }
                const ppChild = p.querySelector('[data-pre-plain-text]');
                if (ppChild && ppChild !== container) { parentPrePlain = ppChild.getAttribute('data-pre-plain-text'); break; }
                p = p.parentElement;
            }

            pttContainers.push({
                classList: container.className.slice(0, 80),
                metaAria, metaText, timeFromText,
                senderAriaLabel, senderTestid, prePlain,
                allAriaLabels, allTextNodes, timeSpans, parentPrePlain,
                outerHtml: container.outerHTML.slice(0, 5000),
            });
        }

        // 7. Buscar TODOS los [data-testid="msg-meta"] en el DOM global
        const allMeta = [...document.querySelectorAll('[data-testid="msg-meta"]')]
            .slice(0, 5).map(e => ({
                ariaLabel: e.getAttribute('aria-label'),
                innerText: e.innerText?.trim(),
                outerHtml: e.outerHTML.slice(0, 300),
            }));

        return { icons, testids, audioEls: audioInfo, noTextSamples, ariaLabels, pttContainers, allMeta };
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


@router.get("/debug/idb/{session_id}", dependencies=[Depends(require_admin)])
async def debug_idb(session_id: str):
    """Diagnóstico temporal: qué databases y stores existen en el IndexedDB de la página WA."""
    page = wa_session._pages.get(session_id)
    if not page:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    result = await page.evaluate("""
    () => new Promise((resolve) => {
        (async () => {
            let info = { databases: [], error: null };
            try {
                const dbs = await indexedDB.databases();
                info.databases = dbs.map(d => d.name);
            } catch(e) {
                info.error = String(e);
                info.databases = ['(no indexedDB.databases() support)'];
            }
            // Intentar abrir cada candidato y listar stores + contar audios
            const details = [];
            const candidates = [...new Set([...info.databases, 'wawc', 'wa-1', 'wawcV2'])];
            for (const name of candidates) {
                await new Promise(res => {
                    const req = indexedDB.open(name);
                    req.onerror = () => { details.push({name, error: 'open failed'}); res(); };
                    req.onsuccess = (e) => {
                        const db = e.target.result;
                        const stores = Array.from(db.objectStoreNames);
                        details.push({name, stores});
                        db.close();
                        res();
                    };
                });
            }
            resolve({databases: info.databases, details});
        })();
    })
    """)
    return result


@router.get("/sync-status", dependencies=[Depends(require_admin)])
async def sync_status():
    """Retorna si hay un sync en curso."""
    return {"running": _sync_running}


class FullSyncBody(BaseModel):
    from_date: Optional[date] = None
    contact_phone: Optional[str] = None


@router.post("/full-sync", dependencies=[Depends(require_admin)])
async def full_sync(background_tasks: BackgroundTasks, body: FullSyncBody = None):
    """
    Scrapea el historial completo de todos los contactos/grupos WA registrados
    y guarda los mensajes históricos en la DB (idempotente — no duplica).
    Acepta from_date y contact_phone opcionales para limitar el scope.
    Corre en background; retorna inmediatamente.
    """
    if body is None:
        body = FullSyncBody()
    background_tasks.add_task(_run_sync, from_date=body.from_date, contact_phone=body.contact_phone)
    return {"ok": True, "message": "Full sync iniciado en background"}


async def _contact_has_summarizer(empresa_id: str, connection_id: str, contact_phone: str) -> bool:
    """
    Devuelve True si hay un flow activo con nodo 'summarize' que aplique
    a este contacto específico (contact_phone) en esta conexión.
    Usa get_active_flows_for_bot para respetar el filtro por contacto.
    """
    from db import get_active_flows_for_bot, get_flow as _get_flow
    flows = await get_active_flows_for_bot(connection_id, contact_phone, empresa_id)
    for f in flows:
        detail = await _get_flow(f["id"])
        if detail:
            nodes = detail.get("definition", {}).get("nodes", [])
            if any(n.get("type") == "summarize" for n in nodes):
                return True
    return False



_sync_running = False


async def _run_sync(from_date: "date | None" = None, contact_phone: "str | None" = None, scroll_rounds: int = 50) -> None:
    global _sync_running
    import logging
    from db import log_message_historic, get_contacts
    from config import get_empresas_for_connection

    _log = logging.getLogger(__name__)
    mode = "full-sync"
    if _sync_running:
        _log.info(f"[{mode}] Ya hay un sync en curso, ignorando.")
        return
    _sync_running = True
    _log.info(f"[{mode}] Iniciando...")
    try:
        total = 0

        for session_id, state in list(clients.items()):
            if state.get("type") != "whatsapp":
                continue
            if state.get("status") != "ready":
                _log.info(f"[{mode}] Sesión {session_id} no está lista, saltando.")
                continue

            bot_phone = session_id
            empresa_ids = get_empresas_for_connection(bot_phone)
            if not empresa_ids:
                empresa_ids = [state.get("connection_id", "")]

            # Solo contactos WA que tienen al menos una tool summarizer activa
            seen_contact_names: set[str] = set()
            contacts_to_sync: list[dict] = []
            for eid in empresa_ids:
                for contact in await get_contacts(eid):
                    if contact["name"] not in seen_contact_names:
                        wa_chs = [ch for ch in contact.get("channels", []) if ch["type"] == "whatsapp"]
                        if not wa_chs:
                            continue
                        # Filtrar por contact_phone si se especificó
                        if contact_phone and not any(ch["value"] == contact_phone for ch in wa_chs):
                            continue
                        contact_wa_phone = wa_chs[0]["value"]
                        has_sum = await _contact_has_summarizer(eid, bot_phone, contact_wa_phone)
                        if not has_sum:
                            _log.info(f"[{mode}] Saltando '{contact['name']}' — sin summarizer activo.")
                            continue
                        seen_contact_names.add(contact["name"])
                        contacts_to_sync.append({"contact": contact, "empresa_ids": empresa_ids, "summarizer_eid": eid})

            # Resetear dedup en memoria antes de acumular (evita falsos positivos por
            # caché stale). NO borrar el .md — preservar mensajes históricos que ya no
            # están en la ventana de scroll de WA Web.
            from graphs.nodes.summarize import _dedup as _sum_dedup, _dedup_loaded as _sum_dedup_loaded, accumulate as _accumulate_msg, get_attachments_dir as _get_att_dir
            for item in contacts_to_sync:
                eid = item["summarizer_eid"]
                for ch in [c for c in item["contact"].get("channels", []) if c["type"] == "whatsapp"]:
                    key = (eid, ch["value"])
                    _sum_dedup_loaded.discard(key)
                    _sum_dedup.pop(key, None)

            for item in contacts_to_sync:
                contact = item["contact"]
                eids = item["empresa_ids"]
                contact_name = contact["name"]
                wa_channels = [ch for ch in contact.get("channels", []) if ch["type"] == "whatsapp"]

                _log.info(f"[{mode}] Scraping '{contact_name}'...")
                # Carpeta para adjuntos: usa el primer canal WA del contacto
                _first_phone = wa_channels[0]["value"] if wa_channels else None
                _doc_dir = _get_att_dir(item["summarizer_eid"], _first_phone) if _first_phone else None
                messages = await wa_session.scrape_full_history(session_id, contact_name, scroll_rounds=scroll_rounds, doc_save_dir=_doc_dir, from_date=from_date)
                # Ordenar cronológicamente antes de acumular: el scrape devuelve
                # textos (Part A) + audios (Part B) concatenados, no mezclados por fecha.
                messages.sort(key=lambda m: m.get("timestamp") or "")

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
                        eid = item["summarizer_eid"]

                        saved = await log_message_historic(
                            eid, bot_phone, phone, contact_name,
                            body, msg["timestamp"], outbound,
                            replace_audio=True,
                        )
                        if saved:
                            total += 1

                        if body and body.strip():
                            from datetime import datetime as _dt
                            try:
                                ts_dt = _dt.strptime(msg["timestamp"], "%Y-%m-%d %H:%M:%S")
                            except (ValueError, TypeError):
                                ts_dt = _dt.now()
                            sum_body = body
                            sum_type = msg.get("msg_type", "text")
                            if sum_body in ("[audio]", "[media]"):
                                sum_body = "[audio — sin blob, requiere descarga manual]"
                                sum_type = "audio"
                            elif sum_body == "[imagen]":
                                sum_body = "[imagen — no disponible]"
                                sum_type = "image"
                            _accumulate_msg(
                                empresa_id=eid,
                                contact_phone=phone,
                                contact_name=contact_name,
                                msg_type=sum_type,
                                content=sum_body,
                                timestamp=ts_dt,
                            )

        _log.info(f"[{mode}] Completado. {total} mensajes nuevos importados.")
    except Exception as _e:
        _log.exception(f"[{mode}] Error inesperado: {_e}")
    finally:
        _sync_running = False


async def _run_delta_sync(contact_phone: "str | None" = None) -> None:
    """
    Sync incremental: para cada contacto con summarizer activo, escanea mensajes
    de más nuevo a más viejo y para en cuanto encuentra uno ya guardado en DB.
    No resetea el .md ni los sumarios — solo agrega lo nuevo.
    Reporta por contacto: cuántos nuevos, dónde paró.
    """
    global _sync_running
    import logging
    from db import log_message_historic, get_contacts
    from config import get_empresas_for_connection

    _log = logging.getLogger(__name__)
    mode = "delta-sync"
    if _sync_running:
        _log.info(f"[{mode}] Ya hay un sync en curso, ignorando.")
        return
    _sync_running = True
    _log.info(f"[{mode}] Iniciando...")
    try:
        for session_id, state in list(clients.items()):
            if state.get("type") != "whatsapp":
                continue
            if state.get("status") != "ready":
                _log.info(f"[{mode}] Sesión {session_id} no está lista, saltando.")
                continue

            bot_phone = session_id
            empresa_ids = get_empresas_for_connection(bot_phone)
            if not empresa_ids:
                empresa_ids = [state.get("connection_id", "")]

            contacts_to_sync: list[dict] = []
            seen_contact_names: set[str] = set()
            for eid in empresa_ids:
                for contact in await get_contacts(eid):
                    if contact["name"] in seen_contact_names:
                        continue
                    wa_chs = [ch for ch in contact.get("channels", []) if ch["type"] == "whatsapp"]
                    if not wa_chs:
                        continue
                    if contact_phone and not any(ch["value"] == contact_phone for ch in wa_chs):
                        continue
                    contact_wa_phone = wa_chs[0]["value"]
                    has_sum = await _contact_has_summarizer(eid, bot_phone, contact_wa_phone)
                    if not has_sum:
                        continue
                    seen_contact_names.add(contact["name"])
                    contacts_to_sync.append({"contact": contact, "empresa_ids": empresa_ids, "summarizer_eid": eid})

            for item in contacts_to_sync:
                contact = item["contact"]
                eids = item["empresa_ids"]
                contact_name = contact["name"]
                wa_channels = [ch for ch in contact.get("channels", []) if ch["type"] == "whatsapp"]

                from graphs.nodes.summarize import get_attachments_dir as _get_att_dir
                _first_phone = wa_channels[0]["value"] if wa_channels else None
                _doc_dir = _get_att_dir(item["summarizer_eid"], _first_phone) if _first_phone else None

                _log.info(f"[{mode}] Escaneando '{contact_name}'...")
                # Scrapear con scroll limitado (delta, no full-history)
                messages = await wa_session.scrape_full_history(
                    session_id, contact_name, scroll_rounds=10, doc_save_dir=_doc_dir
                )
                # Ordenar de más nuevo a más viejo para parar en el primer existente
                messages.sort(key=lambda m: m.get("timestamp") or "", reverse=True)

                new_count = 0
                stop_ts = None
                for msg in messages:
                    for ch in wa_channels:
                        phone = ch["value"]
                        is_group = ch.get("is_group", False)
                        if is_group and msg.get("sender"):
                            body = f"{msg['sender']}: {msg['body']}"
                        else:
                            body = msg["body"]
                        outbound = 1 if msg.get("is_outbound") else 0

                        # Intentar guardar en el primer empresa_id con summarizer
                        eid = item["summarizer_eid"]
                        saved = await log_message_historic(
                            eid, bot_phone, phone, contact_name,
                            body, msg["timestamp"], outbound,
                            replace_audio=True,
                        )
                        if not saved:
                            # Primer mensaje ya existente → este es el punto de corte
                            stop_ts = msg["timestamp"]
                            break
                        new_count += 1

                        if body and body.strip():
                            from datetime import datetime as _dt
                            try:
                                ts_dt = _dt.strptime(msg["timestamp"], "%Y-%m-%d %H:%M:%S")
                            except (ValueError, TypeError):
                                ts_dt = _dt.now()
                            from graphs.compiler import run_flows
                            from graphs.nodes.state import FlowState as _FlowState
                            _state = _FlowState(
                                message=body,
                                message_type=msg.get("msg_type", "text"),
                                contact_phone=phone,
                                contact_name=contact_name,
                                canal="whatsapp",
                                from_delta_sync=True,
                                timestamp=ts_dt,
                            )
                            await run_flows(_state, connection_id=bot_phone)
                    else:
                        continue
                    break  # parar en cuanto un canal encuentra el primer existente

                _log.info(f"[{mode}] '{contact_name}': {new_count} nuevos, paró en {stop_ts or 'tope del chat'}")

        _log.info(f"[{mode}] Completado.")
    except Exception as _e:
        _log.exception(f"[{mode}] Error inesperado: {_e}")
    finally:
        _sync_running = False


@router.post("/refresh", dependencies=[Depends(require_admin)])
async def refresh():
    reconnected = 0
    for session_id, state in clients.items():
        if state.get("type") != "whatsapp":
            continue
        if not await wa_session.is_page_alive(session_id):
            connection_id = state.get("connection_id", "")
            result = await wa_session.connect(session_id, connection_id)
            if result in ("restored", "qr_needed"):
                reconnected += 1
    return {"ok": True, "reconnected": reconnected}


# ------------------------------------------------------------------
# Tarea background: conectar y capturar QR si hace falta
# ------------------------------------------------------------------

def _get_wa_config(config: dict, number: str) -> dict:
    """Extrae connection_id (empresa_id) para un número dado."""
    for empresa in config.get("empresas", []):
        for phone_cfg in empresa.get("phones", []):
            if phone_cfg.get("number") == number:
                return {"connection_id": empresa["id"]}
    return {"connection_id": ""}


async def _connect_and_get_qr(session_id: str, connection_id: str) -> None:
    result = await wa_session.connect(session_id, connection_id)

    if result == "restored":
        # Sesión restaurada — arrancar listener directamente
        cfg = _get_wa_config(load_config(), session_id)
        await wa_session.start_listening(session_id, cfg["connection_id"], session_id)
        return

    if result == "qr_needed":
        qr = await wa_session.get_qr(session_id)
        if qr:
            authenticated = await wa_session.wait_for_auth(session_id)
            if authenticated:
                cfg = _get_wa_config(load_config(), session_id)
                await wa_session.start_listening(session_id, cfg["connection_id"], session_id)
