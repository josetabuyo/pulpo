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

    Busca tanto por la columna connection_id del flow como por el connection_id
    dentro del nodo trigger (pueden diferir si el flow fue creado con un ID genérico).
    """
    from db import get_active_flows_for_bot, get_flow as _get_flow, get_flows as _list_flows
    # Intento 1: búsqueda normal por columna connection_id del flow
    flows = await get_active_flows_for_bot(connection_id, contact_phone, empresa_id)
    for f in flows:
        detail = await _get_flow(f["id"])
        if detail:
            nodes = detail.get("definition", {}).get("nodes", [])
            if any(n.get("type") == "summarize" for n in nodes):
                return True
    # Intento 2: buscar flows de la empresa donde el trigger node usa este connection_id
    # (get_flows no incluye definition — necesitamos get_flow por cada uno)
    all_stubs = await _list_flows(empresa_id)
    for stub in all_stubs:
        if not stub.get("active"):
            continue
        detail = await _get_flow(stub["id"])
        if not detail:
            continue
        nodes = detail.get("definition", {}).get("nodes", [])
        trigger = next(
            (n for n in nodes if n.get("type") in ("whatsapp_trigger", "message_trigger")),
            None,
        )
        if not trigger:
            continue
        if trigger.get("config", {}).get("connection_id") != connection_id:
            continue
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
                messages = await wa_session.scrape_full_history_v2(session_id, contact_name, doc_save_dir=_doc_dir)
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

                # También incluir contactos del included[] de flows activos con summarize
                # (cubren casos como Andrés Buxareo: en el filtro pero nunca mandó mensaje a DB)
                from db import get_flows as _get_flows
                for flow in await _get_flows(eid):
                    if not flow.get("active", False):
                        continue
                    nodes = flow.get("definition", {}).get("nodes", [])
                    has_summarize = any(n.get("type") == "summarize" for n in nodes)
                    if not has_summarize:
                        continue
                    trigger = next((n for n in nodes if n.get("type") == "whatsapp_trigger"), None)
                    if not trigger:
                        continue
                    trigger_conn = trigger.get("config", {}).get("connection_id", "")
                    if trigger_conn and trigger_conn != bot_phone:
                        continue
                    included = trigger.get("config", {}).get("contact_filter", {}).get("included", [])
                    for cname in included:
                        if cname in seen_contact_names:
                            continue
                        if contact_phone and cname != contact_phone:
                            continue
                        seen_contact_names.add(cname)
                        # Sintetizamos un contact-like con el nombre como phone (sin canal real)
                        contacts_to_sync.append({
                            "contact": {"name": cname, "channels": [{"type": "whatsapp", "value": cname}]},
                            "empresa_ids": empresa_ids,
                            "summarizer_eid": eid,
                        })

            for item in contacts_to_sync:
                contact = item["contact"]
                eids = item["empresa_ids"]
                contact_name = contact["name"]
                wa_channels = [ch for ch in contact.get("channels", []) if ch["type"] == "whatsapp"]

                from graphs.nodes.summarize import get_attachments_dir as _get_att_dir
                _first_phone = wa_channels[0]["value"] if wa_channels else None
                _doc_dir = _get_att_dir(item["summarizer_eid"], _first_phone) if _first_phone else None

                _log.info(f"[{mode}] Escaneando '{contact_name}'...")
                # Obtener el timestamp más reciente ya registrado → punto de corte del delta
                _stop_before_ts = None
                if _first_phone:
                    from api.summarizer import _newest_message_ts
                    _stop_before_ts = _newest_message_ts(item["summarizer_eid"], _first_phone)

                messages = await wa_session.scrape_full_history_v2(
                    session_id, contact_name, doc_save_dir=_doc_dir,
                    stop_before_ts=_stop_before_ts,
                )
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


@router.post("/whatsapp/bootstrap-contact", dependencies=[Depends(require_client)])
async def bootstrap_contact(body: dict, background_tasks: BackgroundTasks):
    """
    Raspa el historial de WA de un contacto por nombre y lo guarda en DB.
    Permite importar conversaciones previas sin que el contacto haga nada.

    Body: { "contact_name": str, "empresa_id": str, "connection_id": str }
    """
    import logging
    import asyncio
    from config import get_empresas_for_connection
    from db import log_message_historic

    contact_name = (body.get("contact_name") or "").strip()
    empresa_id   = (body.get("empresa_id")   or "").strip()
    connection_id = (body.get("connection_id") or "").strip()

    if not contact_name or not empresa_id:
        raise HTTPException(status_code=400, detail="contact_name y empresa_id son requeridos")

    # Buscar la sesión WA activa para esta conexión
    session_id = next(
        (sid for sid, st in clients.items()
         if st.get("type") == "whatsapp" and st.get("status") == "ready"
         and (not connection_id or sid == connection_id or st.get("connection_id") == connection_id)),
        None,
    )
    if not session_id:
        raise HTTPException(status_code=503, detail="No hay sesión WhatsApp activa disponible")

    _log = logging.getLogger(__name__)

    async def _do_bootstrap():
        try:
            _log.info("[bootstrap] Iniciando para '%s' (empresa=%s)", contact_name, empresa_id)
            messages = await wa_session.scrape_full_history_v2(session_id, contact_name)
            empresa_ids = get_empresas_for_connection(session_id) or [empresa_id]
            new_count = 0
            for msg in messages:
                if not msg.get("body") or not msg.get("timestamp"):
                    continue
                outbound = 1 if msg.get("is_outbound") else 0
                for eid in empresa_ids:
                    saved = await log_message_historic(
                        eid, session_id, contact_name, contact_name,
                        msg["body"], msg["timestamp"], outbound,
                    )
                    if saved:
                        new_count += 1
            _log.info("[bootstrap] '%s': %d mensajes importados", contact_name, new_count)
        except Exception as e:
            _log.error("[bootstrap] Error para '%s': %s", contact_name, e)

    background_tasks.add_task(_do_bootstrap)
    return {"status": "ok", "message": f"Importando historial de '{contact_name}' en background"}


@router.post("/whatsapp/purge-drafts-session/{number}", dependencies=[Depends(require_admin)])
async def purge_drafts_session(number: str):
    """
    Elimina borradores de la sesión WA del número indicado.
    Útil para limpiar chats con texto residual tras un incidente de envío masivo.
    """
    # Buscar session_id cuyo connection_id coincide con el número
    session_id = next(
        (sid for sid, st in clients.items()
         if st.get("type") == "whatsapp" and st.get("connection_id") == number),
        None,
    )
    if not session_id:
        return {"ok": False, "error": f"No hay sesión activa para {number}"}
    cleared = await wa_session.purge_drafts(session_id)
    return {"ok": True, "cleared": cleared, "session_id": session_id}


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
# Debug de audio: instala interceptor JS + transcribe blobs capturados
# ------------------------------------------------------------------

_BLOB_INTERCEPTOR_JS = """
(function() {
    if (window.__pulpo_debug_installed) return 'already_installed';
    window.__pulpo_debug_installed = true;
    window.__pulpo_captured_blobs = [];
    window.__pulpo_seen_blobs = new Set();

    const origDesc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {
        set(url) {
            if (url && url.startsWith('blob:') && !window.__pulpo_seen_blobs.has(url)) {
                window.__pulpo_seen_blobs.add(url);
                // Buscar contexto del mensaje (pre-plain-text puede estar en ancestros)
                const container = this.closest('[data-pre-plain-text]')
                    || this.closest('[class*="message"]')
                    || this.closest('[class*="_amjl"]');
                const prePlain = container?.getAttribute('data-pre-plain-text') || '';
                window.__pulpo_captured_blobs.push({ url, prePlain, ts: Date.now() });
            }
            if (origDesc?.set) origDesc.set.call(this, url);
        },
        get() { return origDesc?.get ? origDesc.get.call(this) : undefined; },
        configurable: true,
    });
    return 'installed';
})()
"""

_DRAIN_BLOBS_JS = """
() => {
    const items = window.__pulpo_captured_blobs || [];
    window.__pulpo_captured_blobs = [];
    return items;
}
"""

_FETCH_BLOB_JS = """
async (blobUrl) => {
    try {
        const resp = await fetch(blobUrl);
        const buf = await resp.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let bin = '';
        for (let b of bytes) bin += String.fromCharCode(b);
        return btoa(bin);
    } catch(e) { return null; }
}
"""

_LIST_AUDIOS_JS = """
() => {
    // Solo botones reales de play (no ptt-status icons que no son clickeables de la misma forma)
    const btns = document.querySelectorAll(
        'button[aria-label="Reproducir mensaje de voz"], button[aria-label="Play voice message"]'
    );
    const result = [];
    btns.forEach((btn, i) => {
        // Subir al ancestro con data-pre-plain-text o buscar en el contenedor del mensaje
        let prePlain = '';
        let el = btn;
        while (el && el !== document.body) {
            if (el.getAttribute('data-pre-plain-text')) {
                prePlain = el.getAttribute('data-pre-plain-text'); break;
            }
            // Buscar data-pre-plain-text en hijos del mismo contenedor
            const found = el.querySelector('[data-pre-plain-text]');
            if (found) { prePlain = found.getAttribute('data-pre-plain-text'); break; }
            el = el.parentElement;
        }
        const audio = btn.closest('[class]')?.querySelector('audio');
        result.push({
            index: i,
            prePlain,
            hasBlobSrc: audio?.src?.startsWith('blob:') || false,
            blobUrl: audio?.src?.startsWith('blob:') ? audio.src : null,
        });
    });
    return result;
}
"""

_CLICK_AUDIO_JS = """
(index) => {
    const btns = document.querySelectorAll(
        'button[aria-label="Reproducir mensaje de voz"], button[aria-label="Play voice message"]'
    );
    const btn = btns[index];
    if (!btn) return { ok: false, error: 'index out of range', total: btns.length };
    btn.scrollIntoView({ block: 'center', behavior: 'instant' });
    btn.click();
    return { ok: true, clicked: btn.getAttribute('aria-label'), index };
}
"""


@router.post("/debug/eval/{session_id}", dependencies=[Depends(require_admin)])
async def debug_eval(session_id: str, body: dict):
    """
    Evalúa JS arbitrario en el browser headless. Útil para debug interactivo.
    Body: { "js": "() => document.title" }
    El JS se ejecuta con page.evaluate() — puede retornar cualquier valor JSON-serializable.
    """
    js = body.get("js", "")
    if not js:
        raise HTTPException(status_code=400, detail="js requerido")
    page = wa_session._pages.get(session_id)
    if not page:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    try:
        result = await page.evaluate(js)
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


@router.post("/debug/audio/install-interceptor/{session_id}", dependencies=[Depends(require_admin)])
async def debug_install_interceptor(session_id: str):
    """Instala el interceptor JS en el browser para capturar blob URLs de audio."""
    page = wa_session._pages.get(session_id)
    if not page:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    result = await page.evaluate(_BLOB_INTERCEPTOR_JS)
    return {"status": result}


@router.get("/debug/audio/list/{session_id}", dependencies=[Depends(require_admin)])
async def debug_list_audios(session_id: str, chat: str = ""):
    """
    Lista todos los <audio> visibles en el DOM del chat activo.
    Opcional: ?chat=NombreContacto para abrir ese chat primero.
    """
    page = wa_session._pages.get(session_id)
    if not page:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    if chat:
        import unicodedata
        def _norm(s): return unicodedata.normalize("NFKC", s).strip()
        row_handle = await page.evaluate_handle(
            """(target) => {
                const norm = s => s.replace(/[\\u00a0\\u202a\\u202c\\u200e\\u200f]/g,' ').trim();
                const grid = document.querySelector('[role="grid"]');
                if (!grid) return null;
                for (const s of grid.querySelectorAll('span[title]')) {
                    if (norm(s.getAttribute('title')) === norm(target)) {
                        return s.closest('[role="row"]') || s;
                    }
                }
                return null;
            }""",
            _norm(chat),
        )
        if row_handle and not await row_handle.evaluate("el => el === null"):
            await row_handle.scroll_into_view_if_needed()
            await row_handle.click()
            await page.wait_for_timeout(2000)

    audios = await page.evaluate(_LIST_AUDIOS_JS)
    return {"chat": chat, "audios": audios, "count": len(audios)}


@router.post("/debug/audio/click/{session_id}/{index}", dependencies=[Depends(require_admin)])
async def debug_click_audio(session_id: str, index: int):
    """
    Clickea el botón play del audio en la posición [index] del DOM.
    Usar después de install-interceptor para que el blob quede capturado.
    """
    page = wa_session._pages.get(session_id)
    if not page:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    result = await page.evaluate(_CLICK_AUDIO_JS, index)
    await page.wait_for_timeout(2000)
    return result


@router.get("/debug/audio/drain/{session_id}", dependencies=[Depends(require_admin)])
async def debug_drain_blobs(session_id: str):
    """Drena los blob URLs capturados por el interceptor desde la última llamada."""
    page = wa_session._pages.get(session_id)
    if not page:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    blobs = await page.evaluate(_DRAIN_BLOBS_JS)
    return {"blobs": blobs, "count": len(blobs)}


@router.post("/debug/audio/transcribe-blob/{session_id}", dependencies=[Depends(require_admin)])
async def debug_transcribe_blob(session_id: str, body: dict):
    """
    Descarga y transcribe un blob URL capturado.
    Body: { "blob_url": "blob:https://..." }
    """
    import tempfile
    import base64 as _b64
    from pathlib import Path

    blob_url = body.get("blob_url")
    if not blob_url:
        raise HTTPException(status_code=400, detail="blob_url requerido")

    page = wa_session._pages.get(session_id)
    if not page:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    b64 = await page.evaluate(_FETCH_BLOB_JS, blob_url)
    if not b64:
        raise HTTPException(status_code=422, detail="No se pudo descargar el blob (expirado o inaccesible)")

    audio_bytes = _b64.b64decode(b64)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        from tools.transcription import transcribe
        text = await transcribe(tmp_path)
        return {"transcription": text, "blob_url": blob_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al transcribir: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/debug/audio/transcribe-all/{session_id}", dependencies=[Depends(require_admin)])
async def debug_transcribe_all(session_id: str, body: dict = None):
    """
    Todo en uno: instala interceptor, clickea TODOS los audios del chat activo,
    espera que se capturen los blobs y los transcribe.
    Opcional body: { "chat": "Nombre del contacto" }
    Returns: lista de transcripciones con contexto (pre_plain).
    """
    import tempfile
    import base64 as _b64
    import asyncio
    from pathlib import Path

    chat = (body or {}).get("chat", "")
    page = wa_session._pages.get(session_id)
    if not page:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    # 1. Abrir chat si se especificó
    if chat:
        import unicodedata
        def _norm(s): return unicodedata.normalize("NFKC", s).strip()
        row_handle = await page.evaluate_handle(
            """(target) => {
                const norm = s => s.replace(/[\\u00a0\\u202a\\u202c\\u200e\\u200f]/g,' ').trim();
                const grid = document.querySelector('[role="grid"]');
                if (!grid) return null;
                for (const s of grid.querySelectorAll('span[title]')) {
                    if (norm(s.getAttribute('title')) === norm(target)) {
                        return s.closest('[role="row"]') || s;
                    }
                }
                return null;
            }""",
            _norm(chat),
        )
        if row_handle and not await row_handle.evaluate("el => el === null"):
            await row_handle.scroll_into_view_if_needed()
            await row_handle.click()
            await page.wait_for_timeout(2000)

    # 2. Instalar interceptor
    await page.evaluate(_BLOB_INTERCEPTOR_JS)

    # 3. Listar audios
    audios = await page.evaluate(_LIST_AUDIOS_JS)

    results = []
    for audio_info in audios:
        idx = audio_info["index"]
        pre_plain = audio_info["prePlain"]

        # Limpiar blobs anteriores antes de clickear
        await page.evaluate(_DRAIN_BLOBS_JS)

        # Si ya tiene blob cargado, intentar directamente
        if audio_info["blobUrl"]:
            blob_url = audio_info["blobUrl"]
        else:
            # Clickear play y esperar que el interceptor lo capture
            await page.evaluate(_CLICK_AUDIO_JS, idx)
            await page.wait_for_timeout(5000)
            blobs = await page.evaluate(_DRAIN_BLOBS_JS)
            blob_url = blobs[-1]["url"] if blobs else None

        if not blob_url:
            results.append({"index": idx, "prePlain": pre_plain, "error": "blob no capturado"})
            continue

        b64 = await page.evaluate(_FETCH_BLOB_JS, blob_url)
        if not b64:
            results.append({"index": idx, "prePlain": pre_plain, "error": "blob expirado"})
            continue

        audio_bytes = _b64.b64decode(b64)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            from tools.transcription import transcribe
            text = await transcribe(tmp_path)
            results.append({"index": idx, "prePlain": pre_plain, "transcription": text})
        except Exception as e:
            results.append({"index": idx, "prePlain": pre_plain, "error": str(e)})
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return {"chat": chat, "results": results, "total": len(results)}


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
