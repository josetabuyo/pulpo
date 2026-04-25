"""
WhatsAppSession — automatización de WhatsApp Web.

Hereda de BrowserAutomation y agrega los métodos específicos de WhatsApp Web:
  - connect()          → intenta restaurar sesión; si no, navega y pide QR
  - get_qr()           → captura el canvas del QR como PNG base64
  - wait_for_auth()    → espera que el usuario escanee el QR (sesión se guarda sola)
  - start_listening()  → inyecta observer JS que detecta mensajes nuevos
  - is_connected()     → verifica si la sesión está autenticada y activa
  - send_message()     → envía mensaje en página temporal (no interrumpe el observer)

Estrategia de sesión: usa launch_persistent_context() con un directorio de perfil
Chrome completo (data/sessions/{id}/profile/). Preserva cookies, localStorage,
IndexedDB y Service Workers — todo lo que WA Web necesita para no pedir QR de nuevo.
El perfil se guarda automáticamente; no hace falta llamar save_session() manualmente.
"""

import asyncio
import base64
import logging
from pathlib import Path

from automation.browser import BrowserAutomation
from state import clients

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path("data/sessions")
WA_URL = "https://web.whatsapp.com/"

# Timeouts
QR_APPEAR_TIMEOUT_MS = 60_000   # tiempo máximo para que aparezca el QR
QR_SCAN_TIMEOUT_MS   = 120_000  # tiempo máximo para que el usuario escanee
SEND_TIMEOUT_MS      = 15_000


class WhatsAppSession(BrowserAutomation):
    """
    Una instancia gestiona TODAS las sesiones de WhatsApp del servidor.
    Una pestaña (Page) por teléfono, dentro del mismo browser.
    """

    # ------------------------------------------------------------------
    # Sesión persistente (perfil Chrome completo)
    # ------------------------------------------------------------------

    async def _open_wa_session(self, session_id: str) -> "Page":
        """
        Abre (o reutiliza) un contexto persistente de Chromium con el perfil
        completo del browser guardado en data/sessions/{session_id}/profile/.

        A diferencia de new_context() + storage_state(), este perfil preserva
        cookies, localStorage, IndexedDB y Service Workers — todo lo que WA Web
        necesita para restaurar la sesión sin pedir QR de nuevo.
        """
        if session_id in self._pages:
            return self._pages[session_id]

        profile_dir = str(SESSIONS_DIR / session_id / "profile")
        Path(profile_dir).mkdir(parents=True, exist_ok=True)

        context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--remote-debugging-port=9222",  # permite inspección vía chrome://inspect
            ],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="es-AR",
        )
        # Quitar navigator.webdriver para que WA Web no detecte automatización
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = context.pages[0] if context.pages else await context.new_page()
        self._contexts[session_id] = context
        self._pages[session_id] = page

        # Listeners de diagnóstico — visibles en el log del backend
        def _on_console(msg):
            text = msg.text
            # Caídas de WebSocket y red: WARNING para que sean visibles en el monitor
            if "ERR_NAME_NOT_RESOLVED" in text or "ERR_NETWORK_CHANGED" in text:
                logger.warning(f"[{session_id}] ⚠️ Red caída: {text[:120]}")
            elif "WebSocket connection" in text and "failed" in text:
                logger.warning(f"[{session_id}] ⚠️ WebSocket desconectado — posibles mensajes perdidos")
            else:
                logger.debug(f"[{session_id}][browser] {msg.type}: {text}")

        page.on("console", _on_console)
        page.on("pageerror", lambda err: logger.error(f"[{session_id}][browser:error] {err}"))
        page.on("load", lambda: logger.info(f"[{session_id}] Página cargada: {page.url}"))
        page.on("crash", lambda: logger.error(f"[{session_id}] ¡La página crasheó!"))
        context.on("weberror", lambda e: logger.error(f"[{session_id}][weberror] {e.error}"))

        logger.info(f"[{session_id}] Perfil persistente abierto en {profile_dir}")
        return page

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------

    async def connect(self, session_id: str, connection_id: str) -> str:
        """
        Intenta conectar la sesión usando el perfil Chrome persistente:
          1. Si el perfil en disco tiene sesión válida → la restaura.
          2. Si no → navega a WA Web y espera QR.

        Espera a que aparezca la UI principal (autenticado) O el QR,
        lo que llegue primero. Evita falsos positivos durante la carga.

        Retorna: "restored" | "qr_needed" | "failed"
        """
        _update(session_id, connection_id=connection_id, status="connecting")

        # Selectores precisos — NO usar canvas genérico que matchea elementos de carga
        SELECTORS_AUTHED = "[data-testid='chat-list'], #side, [data-testid='search-input']"
        SELECTORS_QR     = "[data-testid='qrcode'], div[data-ref], canvas"

        # Cerrar sesión previa si existía (importante en reintentos)
        await self.close_session(session_id)

        try:
            await self.ensure_launched()
            page = await self._open_wa_session(session_id)
            await page.goto(WA_URL, wait_until="domcontentloaded", timeout=30_000)

            # Esperar hasta 90s a que aparezca la UI principal O el QR
            try:
                await page.wait_for_selector(
                    f"{SELECTORS_AUTHED}, {SELECTORS_QR}",
                    timeout=90_000,
                )
            except Exception:
                logger.error(f"[{session_id}] WA Web no cargó en 90s")
                _update(session_id, status="failed")
                await self.close_session(session_id)
                return "failed"

            # Ahora determinar qué apareció
            is_qr = await page.query_selector(SELECTORS_QR)
            if is_qr:
                _update(session_id, status="qr_needed")
                logger.info(f"[{session_id}] QR requerido.")
                return "qr_needed"
            else:
                _update(session_id, status="ready")
                logger.info(f"[{session_id}] Sesión restaurada correctamente.")
                return "restored"

        except Exception as e:
            logger.error(f"[{session_id}] Error al conectar: {e}")
            _update(session_id, status="failed")
            await self.close_session(session_id)
            return "failed"

    # ------------------------------------------------------------------
    # QR
    # ------------------------------------------------------------------

    async def get_qr(self, session_id: str) -> str | None:
        """Captura el canvas del QR como PNG base64."""
        page = self.get_page(session_id)
        if not page:
            return None
        try:
            canvas = page.locator("canvas").first
            await canvas.wait_for(state="visible", timeout=QR_APPEAR_TIMEOUT_MS)
            qr_bytes = await canvas.screenshot(type="png")
            qr_b64 = "data:image/png;base64," + base64.b64encode(qr_bytes).decode()
            _update(session_id, status="qr_ready", qr=qr_b64)
            logger.info(f"[{session_id}] QR capturado.")
            return qr_b64
        except Exception as e:
            logger.error(f"[{session_id}] Error capturando QR: {e}")
            _update(session_id, status="failed")
            return None

    async def wait_for_auth(self, session_id: str) -> bool:
        """
        Espera hasta que el usuario escanee el QR.
        Con perfil persistente, Chrome guarda la sesión en disco automáticamente;
        no hace falta llamar save_session().
        """
        page = self.get_page(session_id)
        if not page:
            return False
        try:
            # Esperar que el QR desaparezca (usuario escaneó)
            await page.wait_for_selector(
                "[data-testid='qrcode'], div[data-ref]",
                state="hidden",
                timeout=QR_SCAN_TIMEOUT_MS,
            )
            # Confirmar que la UI principal cargó
            await page.wait_for_selector(
                "[data-testid='chat-list'], #side, [data-testid='search-input']",
                timeout=15_000,
            )
            # El perfil Chrome ya se guardó solo — no hace falta save_session()
            _update(session_id, status="ready", qr=None)
            logger.info(f"[{session_id}] Autenticado. Perfil guardado en disco automáticamente.")
            return True
        except Exception as e:
            logger.warning(f"[{session_id}] Error esperando autenticación: {e}")
            _update(session_id, status="qr_needed")
            return False

    # ------------------------------------------------------------------
    # Listener de mensajes
    # ------------------------------------------------------------------

    async def start_listening(
        self,
        session_id: str,
        bot_id: str,
        bot_phone: str,
    ) -> None:
        """
        Inyecta un observer JS en la página principal de WA Web que detecta
        chats con mensajes no leídos. Por cada mensaje nuevo llama al handler
        Python que loguea en DB y responde según herramientas activas.
        """
        page = self.get_page(session_id)
        if not page:
            logger.warning(f"[{session_id}] start_listening: no hay página activa")
            return

        # Importación diferida para evitar ciclo circular
        from db import log_message, mark_answered
        from config import get_empresas_for_connection

        recent_msgs: set[tuple[str, str]] = set()  # dedup entre JS y Python poll

        async def _on_message(phone: str, name: str, body: str, from_poll: bool = False, wa_ts_str: str = "") -> None:
            # Filtrar placeholders de carga de WA Web ("Cargando...", etc.)
            _LOADING_BODIES = {"Cargando...", "Loading...", "Cargando…", "Loading…"}
            if body.strip() in _LOADING_BODIES:
                return

            # Dedup: mismo (name, body) ya procesado recientemente.
            # from_poll=True viene del polling Python (sidebar preview): no agrega al
            # dedup compartido para no bloquear al listener JS que puede llegar después
            # con el cuerpo completo del mensaje (y sí debe pasar al summarizer).
            pair = (name, body)
            if pair in recent_msgs:
                return
            if not from_poll:
                recent_msgs.add(pair)
                asyncio.get_event_loop().call_later(60, lambda: recent_msgs.discard(pair))

            # WA usa el nombre como identificador (phone suele llegar vacío del scraper)
            sender = phone or name

            # Pre-filtro: solo procesar mensajes de contactos que pasan algún filtro activo.
            # Si la conexión tiene flows con contact_filter y este contacto no califica
            # en ninguno → descartar silencioso (sin log, sin DB, sin reply).
            if not await _passes_any_flow_filter(bot_phone, name, phone):
                logger.debug(f"[{session_id}] descartado (sin filtro activo): {name} ({phone})")
                return

            logger.info(f"[{session_id}] Mensaje de {name} ({phone}): {body[:60]}")

            # Dispatch multi-empresa: loguar bajo todos los bots que tienen esta conexión
            empresa_ids = get_empresas_for_connection(bot_phone)
            if not empresa_ids:
                empresa_ids = [bot_id]

            msg_ids = {}
            for eid in empresa_ids:
                mid = await log_message(eid, bot_phone, phone or name, name, body)
                msg_ids[eid] = mid

            # Normalizar tipo de mensaje y resolver contacto
            from db import find_contact_by_channel, get_contacts
            contact = await find_contact_by_channel("whatsapp", sender)

            # Fallback: si WA no dio teléfono (contacto guardado), buscar por nombre
            if not contact and not phone:
                for eid in empresa_ids:
                    all_contacts = await get_contacts(eid)
                    contact = next((c for c in all_contacts if c["name"] == name), None)
                    if contact:
                        break

            if contact and not phone:
                _wa = next((c for c in contact.get("channels", [])
                            if c["type"] == "whatsapp" and not c.get("is_group")), None)
                if _wa:
                    sender = _wa["value"]

            # Parsear mensajes de grupo: "NombreIntegrante: texto"
            sender_in_group: str | None = None
            if contact:
                ch = next((c for c in contact.get("channels", [])
                           if c["type"] == "whatsapp" and c.get("is_group")), None)
                if ch and ": " in body:
                    parts = body.split(": ", 1)
                    sender_in_group = parts[0].strip()
                    body = parts[1].strip()

            # Detectar tipo de mensaje WA
            import re as _re
            _AUDIO_MARKERS = ("🎵", "🎤", "Audio", "audio", "Voice message",
                              "Mensaje de audio", "Mensaje de voz", "[audio:]")
            is_audio = any(m in body for m in _AUDIO_MARKERS) or bool(_re.match(r'^\d{1,2}:\d{2}$', body))
            _is_document = body.startswith('[doc:')
            _is_image = body == '[img:]'

            msg_text = body
            msg_type = "text"
            attachment_path: str | None = None

            if not from_poll:
                if is_audio:
                    audio_dl = await self._download_audio_blob(page, name, session_id)
                    if not audio_dl:
                        # Fallback IDB: buscar el audio más reciente en IndexedDB (recibido en los últimos 5 min)
                        import time as _live_time
                        _now = int(_live_time.time())
                        idb_keys = await self._fetch_audio_idb_keys(page, session_id)
                        recent = [k for k in idb_keys if (_now - k["t"]) < 300]
                        if recent:
                            # El más reciente es el que acaba de llegar
                            best = max(recent, key=lambda k: k["t"])
                            audio_dl = await self._download_decrypt_audio_cdn(
                                best["directPath"], best["mediaKey"], session_id
                            )
                            if audio_dl:
                                logger.info(f"[{session_id}] Audio live: IDB fallback OK para {name}")
                    if audio_dl:
                        # Pasar el archivo al flow — el nodo transcribe_audio se encarga
                        attachment_path = audio_dl
                        msg_text = ""
                    else:
                        msg_text = "[audio — no disponible]"
                    msg_type = "audio"
                elif _is_document:
                    inner = body[5:].rstrip(']')
                    _doc_fn = inner.split('|')[0] if '|' in inner else inner
                    msg_text = f"`{_doc_fn}` ({inner.replace('|', ' ').replace('·', ' · ')})" if '|' in inner else f"`{inner}`"
                    msg_type = "document"
                    # Descargar a temp — SummarizeNode lo moverá a storage permanente
                    import tempfile, shutil
                    _tmp_dir = tempfile.mkdtemp()
                    _tmp_path = Path(_tmp_dir) / _doc_fn
                    await self._download_document_from_page(page, _doc_fn, _tmp_path)
                    if _tmp_path.exists():
                        attachment_path = str(_tmp_path)
                elif _is_image:
                    img_dl = await self._download_image_blob(page, name, session_id)
                    if img_dl:
                        msg_text = f"[imagen guardada: {img_dl.name}]"
                        attachment_path = str(img_dl)
                    else:
                        msg_text = "[imagen — no disponible]"
                    msg_type = "image"

            # Para grupos: incluir remitente en el texto.
            # Si es audio con blob descargado (msg_text vacío), NO prepender aquí —
            # TranscribeAudioNode vería "Nombre: " como texto real y saltaría la transcripción.
            # En ese caso, group_sender se pasa en FlowState y SummarizeNode lo prepende después.
            if sender_in_group and msg_text:
                msg_text = f"{sender_in_group}: {msg_text}"

            # Parsear timestamp real del mensaje si viene del DOM de WA Web.
            # Previene que accumulate() use datetime.now() para mensajes re-entregados.
            _msg_ts = None
            if wa_ts_str:
                from datetime import datetime as _dt_parse
                import re as _re_ts
                # WA usa formato "H:MM p. m., D/M/YYYY" o "H:MM AM, M/D/YYYY"
                # Limpiar: quitar puntos de "p. m." → "PM", etc.
                _cleaned = (_re_ts.sub(r'\bp\.\s*m\.\b', 'PM', wa_ts_str, flags=_re_ts.IGNORECASE)
                            .replace('a. m.', 'AM').replace('A. M.', 'AM'))
                for _fmt in ("%I:%M %p, %d/%m/%Y", "%I:%M %p, %m/%d/%Y",
                             "%H:%M, %d/%m/%Y", "%H:%M, %m/%d/%Y"):
                    try:
                        _msg_ts = _dt_parse.strptime(_cleaned.strip(), _fmt)
                        break
                    except ValueError:
                        pass

            # Flow engine
            from graphs.compiler import run_flows
            from graphs.nodes.state import FlowState

            state = FlowState(
                message=msg_text,
                message_type=msg_type,
                attachment_path=attachment_path,
                contact_phone=sender,
                contact_name=name,
                canal="whatsapp",
                from_poll=from_poll,
                group_sender=sender_in_group if sender_in_group and not msg_text else "",
                timestamp=_msg_ts,
            )
            state = await run_flows(state, connection_id=session_id)
            reply = state.reply or ""

            if not reply or body.strip() == reply.strip():
                return

            # Enviamos en página temporal para no interrumpir el observer
            target = phone if phone else name
            ok = await self.send_message(session_id, target, reply)
            if ok:
                logger.info(f"[{session_id}] → Respuesta enviada a '{name}': {reply[:200]}")
                for mid in msg_ids.values():
                    await mark_answered(mid)

        # Exponer callback Python → JS (falla silencioso si ya fue expuesto)
        try:
            await page.expose_function("__waOnMessage", _on_message)
        except Exception:
            pass

        # Script JS: observa badges de no leídos en sidebar Y mensajes del chat abierto
        await page.evaluate("""
        (() => {
            if (window.__waListenerRunning) return;
            window.__waListenerRunning = true;

            const seen = new Set();
            let lastOpenChatKey = '';
            const lastPreview = {};   // name → último body visto en sidebar
            // Warmup: no disparar mensajes durante los primeros 30s tras arranque.
            // sidebarReady=false inicializa lastPreview sin disparar.
            // readyAt es el timestamp a partir del cual sí se procesan.
            let sidebarReady = false;
            const readyAt = Date.now() + 30000;

            function extractPhone(el) {
                const anchor = el.closest('[data-id]') || el.closest('a[href]');
                if (!anchor) return '';
                const raw = anchor.getAttribute('data-id') || anchor.getAttribute('href') || '';
                const m = raw.match(/(\\d{8,15})/);
                return m ? m[1] : '';
            }

            // ── 1. Sidebar: preview cambió (WA Web usa role=grid/row + span[title]) ─
            async function pollSidebar() {
                const grid = document.querySelector('[role="grid"]');
                if (!grid) return;
                const rows = grid.querySelectorAll('[role="row"]');

                for (const row of rows) {
                    const spans = row.querySelectorAll('span[title]');
                    if (spans.length < 2) continue;

                    const name = spans[0].getAttribute('title').trim();
                    const body = spans[1].getAttribute('title').replace(/[\\u202a\\u202c]/g, '').trim();
                    if (!name || !body) continue;

                    // Durante warmup: solo registrar estado, no disparar nunca.
                    // Después del warmup: detectar cambios reales (mensajes nuevos).
                    const inWarmup = !sidebarReady || Date.now() < readyAt;
                    if (inWarmup) { lastPreview[name] = body; continue; }

                    const changed = lastPreview[name] !== body;
                    lastPreview[name] = body;
                    if (!changed) continue;

                    // Saltar si el último mensaje es saliente.
                    // En el sidebar WA Web usa data-icon="status-dblcheck/check/time"
                    const isOutgoing = !!row.querySelector('[data-icon^="status-"]');
                    if (isOutgoing) continue;

                    const key = 'sidebar|' + name + '|' + body;
                    if (seen.has(key)) continue;
                    seen.add(key);
                    setTimeout(() => seen.delete(key), 60000);

                    try { await __waOnMessage('', name, body, true); }
                    catch(e) { console.error('[Bot] Error (sidebar):', e); }
                }

                sidebarReady = true;
            }

            // ── 2. Chat abierto: nuevo mensaje en el panel (por conteo) ───
            async function pollOpenChat() {
                // Nombre del contacto en el header de la conversación
                const nameEl = document.querySelector(
                    'header [data-testid="conversation-info-header"] span[title], ' +
                    'header span[dir="auto"][title], ' +
                    'header ._amid span[title]'
                );
                const name = (nameEl?.getAttribute('title') || nameEl?.textContent || '').trim();
                if (!name) return;

                // Todos los mensajes visibles en el panel
                const allMsgs = document.querySelectorAll('[data-testid="msg-container"]');
                if (!allMsgs.length) return;

                // Tomar el último mensaje e ignorar si es saliente (del operador)
                const lastMsg = allMsgs[allMsgs.length - 1];
                const isOutgoing = !!lastMsg.querySelector('[data-icon^="msg-"]');
                if (isOutgoing) return;

                // Extracción con soporte de replies (mismo patrón que full-sync)
                const ppEl = lastMsg.querySelector('[data-pre-plain-text]');
                const msgRoot = ppEl || lastMsg;
                const children = [...msgRoot.children];
                let body = '';
                if (children.length >= 2) {
                    const realEl = children[children.length - 1].querySelector('span.copyable-text, [data-testid="selectable-text"]');
                    body = realEl ? realEl.innerText.trim() : '';
                    const qb = children[0];
                    const quotedText = qb.querySelector('span.copyable-text, [data-testid="selectable-text"]');
                    const quotedBody = quotedText ? quotedText.innerText.trim() : '';
                    if (quotedBody) {
                        // Capturar sender del mensaje citado (mismo patrón que senders de grupo)
                        let quotedSender = '';
                        const qsAuthor = qb.querySelector('[data-testid="author"]');
                        const qsColor  = qb.querySelector('span[style*="color:#"], span[style*="color: #"]');
                        const qsDir    = qb.querySelector('span[dir="ltr"]:not(.copyable-text), span[dir="auto"]:not(.copyable-text)');
                        if (qsAuthor) quotedSender = qsAuthor.innerText.trim();
                        else if (qsColor) quotedSender = qsColor.innerText.trim();
                        else if (qsDir) {
                            const t = qsDir.innerText.trim();
                            if (t && t.length < 60 && t !== quotedBody) quotedSender = t;
                        }
                        const replyMeta = quotedSender ? '[' + quotedSender + '] ' : '';
                        body = body + '\\n> ↩ ' + replyMeta + quotedBody;
                    }
                } else {
                    const textEl = msgRoot.querySelector('span.copyable-text, [data-testid="msg-text"]');
                    body = textEl ? textEl.innerText.trim() : '';
                }
                // Si body vacío, verificar si es un documento compartido
                if (!body) {
                    const docBtn = lastMsg.querySelector('div[role="button"][title^="Descargar"]');
                    if (docBtn) {
                        const fn = docBtn.title.replace(/^Descargar\\s*"?/, '').replace(/"$/, '').trim();
                        const inner = (docBtn.innerText || '').split('\\n');
                        const sz = (inner[2] || '').split('•')[1]?.trim() || '';
                        const ext = fn.split('.').pop().toUpperCase();
                        body = sz ? '[doc:' + fn + '|' + ext + '·' + sz + ']' : '[doc:' + fn + ']';
                    }
                }
                // Si body vacío, verificar si es una imagen
                if (!body) {
                    const imgEl = lastMsg.querySelector('img[src^="blob:"]');
                    if (imgEl) {
                        body = '[img:]';
                    }
                }
                // Si body vacío, verificar si es un audio/PTT
                if (!body) {
                    const audioEl = lastMsg.querySelector(
                        '[data-icon="audio-play"], [data-icon="ptt-status"], ' +
                        '[data-testid="audio-play"], [data-testid="ptt-status"]'
                    );
                    if (audioEl) {
                        const durEl = lastMsg.querySelector('[data-testid="audio-duration"], span[aria-label]');
                        const dur = durEl?.textContent?.trim() || '';
                        body = /^\d{1,2}:\d{2}$/.test(dur) ? dur : '[audio:]';
                    }
                }
                if (!body) return;

                // Timestamp real del mensaje (para dedup persistente en summarizer)
                const ppEl2 = lastMsg.querySelector('[data-pre-plain-text]');
                const waTs = ppEl2 ? (ppEl2.getAttribute('data-pre-plain-text').match(/\[([^\]]+)\]/) || [])[1] || '' : '';

                // Key por conteo + texto: detecta mensajes nuevos aunque el texto sea igual
                const key = 'open|' + name + '|' + allMsgs.length + '|' + body;
                if (key === lastOpenChatKey) return;
                lastOpenChatKey = key;

                if (seen.has(key)) return;
                seen.add(key);
                setTimeout(() => seen.delete(key), 60000);

                try { await __waOnMessage('', name, body, false, waTs); }
                catch(e) { console.error('[Bot] Error (open chat):', e); }
            }

            async function poll() {
                await pollSidebar();
                await pollOpenChat();
            }

            setInterval(poll, 2000);
            console.log('[Bot] Listener de mensajes activo (sidebar + chat abierto).');
        })();
        """)

        logger.info(f"[{session_id}] Listener de mensajes activo.")

        # Polling Python: detecta el último mensaje del chat abierto
        # Más robusto que el JS inyectado — usa evaluate() con múltiples fallbacks
        asyncio.create_task(self._poll_open_chat(session_id, page, _on_message))
        asyncio.create_task(self._poll_sidebar_for_delta(session_id, page, bot_id, bot_phone))

    async def _poll_open_chat(self, session_id: str, page, on_message) -> None:
        """
        Corre en background: cada 3s evalúa JS en la página WA para obtener
        el último mensaje del chat abierto y llama al handler Python.
        Cubre el caso de 'Message yourself' y chats que no tienen badge de no leídos.
        """
        seen_pairs: set[tuple[str, str]] = set()  # (name, body) ya procesados
        import time as _pt
        _poll_start = _pt.time()
        _POLL_WARMUP_SECS = 30  # igual que el warmup del listener JS: no disparar al arranque
        logger.info(f"[{session_id}] _poll_open_chat iniciado.")
        while True:
            await asyncio.sleep(3)
            try:
                if page.is_closed():
                    break
                result = await page.evaluate("""
                () => {
                    // WA Web: role="grid" para la lista, role="row" para cada chat.
                    // Cada row tiene span[title]: primero el nombre, luego el preview.
                    const grid = document.querySelector('[role="grid"]');
                    if (!grid) return null;

                    const rows = grid.querySelectorAll('[role="row"]');
                    if (!rows.length) return null;

                    // Recopilar TODOS los chats (nombre + preview + phone)
                    const chats = [];
                    for (const row of rows) {
                        const spans = row.querySelectorAll('span[title]');
                        if (spans.length < 2) continue;
                        const name = spans[0].getAttribute('title').trim();
                        const body = spans[1].getAttribute('title')
                            .replace(/[\\u202a\\u202c\\u200e\\u200f]/g, '').trim();
                        if (!name || !body) continue;

                        // Saltar si el último mensaje es saliente
                        // En el sidebar WA Web usa data-icon="status-dblcheck/check/time"
                        const isOutgoing = !!row.querySelector('[data-icon^="status-"]');
                        if (isOutgoing) continue;

                        // Extraer número de teléfono del atributo data-id.
                        // WA puede tener data-id en el row mismo, en un padre directo,
                        // o en un ancestro más lejano — probar todas las variantes.
                        const rawId = row.getAttribute('data-id')
                            || row.parentElement?.getAttribute('data-id')
                            || row.parentElement?.parentElement?.getAttribute('data-id')
                            || (row.closest('[data-id]') ? row.closest('[data-id]').getAttribute('data-id') : '')
                            || (row.querySelector('[data-id]') ? row.querySelector('[data-id]').getAttribute('data-id') : '')
                            || '';
                        const phoneMatch = rawId ? rawId.match(/(\\d{8,15})/) : null;
                        const phone = phoneMatch ? phoneMatch[1] : '';

                        // Timestamp del último mensaje (del sidebar, no del chat abierto)
                        const tsEl = row.querySelector('[data-testid="last-msg-status"] ~ span, .x1rg5ohu span[dir]');
                        const waTs = tsEl ? tsEl.textContent.trim() : '';
                        chats.push({ name, body, phone, waTs });
                    }
                    if (!chats.length) return null;
                    return { chats, count: rows.length };
                }
                """)

                if not result:
                    continue

                # Comparar cada chat con su último preview conocido
                in_warmup = _pt.time() - _poll_start < _POLL_WARMUP_SECS
                for chat in result["chats"]:
                    name, body, phone = chat["name"], chat["body"], chat.get("phone", "")
                    pair = (name, body)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    if in_warmup:
                        # Warmup: registrar el estado inicial sin disparar auto-replies.
                        # Evita responder mensajes que ya estaban en el chat al arrancar.
                        logger.debug(f"[{session_id}] open-chat warmup: {name} → {body[:40]}")
                        continue
                    logger.debug(f"[{session_id}] open-chat detectó: {name} ({phone}) → {body[:40]}")
                    wa_ts = chat.get("waTs", "")
                    await on_message(phone, name, body, from_poll=True, wa_ts_str=wa_ts)

            except Exception as e:
                if "closed" in str(e).lower() or "target" in str(e).lower():
                    break
                logger.info(f"[{session_id}] _poll_open_chat error: {e}")

    async def _poll_sidebar_for_delta(
        self, session_id: str, page, bot_id: str, bot_phone: str
    ) -> None:
        """
        Corre cada 10s: lee el preview del sidebar para cada contacto monitoreado
        y lo compara con el último mensaje guardado en DB.
        Si difiere → dispara _run_delta_sync para ese contacto.
        Captura tanto mensajes entrantes (sin badge si ya leídos) como salientes
        (enviados desde otro dispositivo/WA Desktop).
        """
        from db import get_last_message_body, get_contacts
        from config import get_empresas_for_connection

        # Previews que ya triggereamos delta-sync: evita disparar dos veces el mismo cambio
        _triggered: dict[str, str] = {}  # phone → preview que disparó el último sync

        while True:
            await asyncio.sleep(10)
            try:
                if page.is_closed():
                    break

                # Leer previews del sidebar incluyendo mensajes salientes
                chats = await page.evaluate("""
                () => {
                    const grid = document.querySelector('[role="grid"]');
                    if (!grid) return [];
                    const result = [];
                    for (const row of grid.querySelectorAll('[role="row"]')) {
                        const spans = row.querySelectorAll('span[title]');
                        if (spans.length < 2) continue;
                        const name = spans[0].getAttribute('title').trim();
                        const preview = spans[1].getAttribute('title')
                            .replace(/[\u202a\u202c\u200e\u200f]/g, '').trim();
                        if (!name || !preview) continue;
                        const rawId = row.getAttribute('data-id')
                            || row.parentElement?.getAttribute('data-id')
                            || row.parentElement?.parentElement?.getAttribute('data-id')
                            || (row.closest('[data-id]') ? row.closest('[data-id]').getAttribute('data-id') : '')
                            || (row.querySelector('[data-id]') ? row.querySelector('[data-id]').getAttribute('data-id') : '')
                            || '';
                        const phoneMatch = rawId ? rawId.match(/(\d{8,15})/) : null;
                        const phone = phoneMatch ? phoneMatch[1] : '';
                        result.push({ name, preview, phone });
                    }
                    return result;
                }
                """)

                if not chats:
                    continue

                empresa_ids = get_empresas_for_connection(bot_phone) or [bot_id]
                eid = empresa_ids[0]

                for chat in chats:
                    name = chat["name"]
                    preview_raw = chat["preview"]
                    phone = chat.get("phone", "")
                    if not phone:
                        continue

                    # Verificar si hay flows activos para este contacto
                    from db import get_active_flows_for_bot
                    from config import get_empresas_for_connection as _get_emps
                    _eids = _get_emps(session_id)
                    _has_flows = any(
                        await get_active_flows_for_bot(session_id, phone, eid)
                        for eid in _eids
                    ) if _eids else False
                    if not _has_flows:
                        continue

                    # Normalizar preview: quitar prefijo "Tú: " (mensaje saliente)
                    preview_norm = preview_raw
                    for prefix in ("Tú: ", "Tu: ", "You: "):
                        if preview_norm.startswith(prefix):
                            preview_norm = preview_norm[len(prefix):]
                            break

                    # Truncar a 35 chars para comparación robusta
                    preview_trunc = preview_norm[:35].strip()

                    # Comparar con último body en DB
                    last_body = await get_last_message_body(eid, phone) or ""
                    last_trunc = last_body[:35].strip()

                    if preview_trunc == last_trunc:
                        continue  # sin cambios

                    # Si ya triggereamos sync para este mismo preview, no repetir
                    if _triggered.get(phone) == preview_trunc:
                        continue

                    _triggered[phone] = preview_trunc
                    logger.info(
                        f"[{session_id}] sidebar-delta: '{name}' cambió preview → disparando delta-sync"
                    )
                    from api.whatsapp import _run_delta_sync
                    asyncio.create_task(_run_delta_sync(contact_phone=phone))

            except Exception as e:
                if "closed" in str(e).lower() or "target" in str(e).lower():
                    break
                logger.debug(f"[{session_id}] _poll_sidebar_for_delta error: {e}")

    # ------------------------------------------------------------------
    # Descarga de audio desde WA Web
    # ------------------------------------------------------------------

    async def _download_audio_blob(
        self, page, sender_name: str, session_id: str
    ) -> str | None:
        """
        Abre el chat del remitente, localiza el último mensaje de audio en el panel,
        fuerza la carga del blob clickeando play si hace falta, y descarga los bytes.

        Retorna la ruta de un archivo temporal /tmp/pulpo_audio_*.ogg, o None si falla.
        El caller es responsable de eliminar el archivo tras la transcripción.
        """
        import time
        import base64 as _b64

        try:
            # 1. Abrir el chat del remitente (mismo patrón que send_message)
            contact_span = page.locator(
                f"[role='grid'] span[title='{sender_name}']"
            ).first
            await contact_span.wait_for(state="visible", timeout=5000)
            await contact_span.click()
            await page.wait_for_timeout(1000)

            # 2. Buscar el último mensaje de audio y descargar su blob
            blob_b64 = await page.evaluate("""
            async () => {
                const tryFetch = async (audio) => {
                    if (!audio.src || !audio.src.startsWith('blob:')) return null;
                    try {
                        const resp = await fetch(audio.src);
                        const buf  = await resp.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        let bin = '';
                        for (let b of bytes) bin += String.fromCharCode(b);
                        return btoa(bin);
                    } catch(e) { return null; }
                };

                const msgs = document.querySelectorAll('[data-testid="msg-container"]');
                if (!msgs.length) return null;

                // Recorrer desde el último mensaje hacia atrás
                for (let i = msgs.length - 1; i >= 0; i--) {
                    const audio = msgs[i].querySelector('audio');
                    if (!audio) continue;

                    // Intentar con blob ya cargado
                    let b64 = await tryFetch(audio);
                    if (b64) return b64;

                    // Blob no cargado: intentar clickear el play para forzar descarga
                    const playBtn = msgs[i].querySelector(
                        'button[aria-label*="voz"], button[aria-label*="voice"], ' +
                        'button[aria-label*="Voice"], button[aria-label*="Reproducir"], ' +
                        'button[aria-label*="reproducir"], button[aria-label*="Escuchar"], ' +
                        '[data-icon="ptt-status"], [data-testid="audio-play"], [data-icon="audio-play"]'
                    );
                    if (playBtn) {
                        playBtn.click();
                        // Polling hasta 6s esperando que se rellene audio.src
                        await new Promise(resolve => {
                            let elapsed = 0;
                            const iv = setInterval(() => {
                                elapsed += 200;
                                if ((audio.src && audio.src.startsWith('blob:')) || elapsed >= 6000) {
                                    clearInterval(iv);
                                    resolve();
                                }
                            }, 200);
                        });
                        b64 = await tryFetch(audio);
                        if (b64) {
                            audio.pause();  // no reproducir en producción
                            return b64;
                        }
                    }
                    break;  // solo intentar con el último mensaje de audio
                }
                return null;
            }
            """)

            if not blob_b64:
                logger.debug(f"[{session_id}] _download_audio_blob: sin blob para {sender_name}")
                return None

            path = f"/tmp/pulpo_audio_{int(time.time() * 1000)}.ogg"
            with open(path, "wb") as f:
                f.write(_b64.b64decode(blob_b64))
            logger.info(f"[{session_id}] Blob de audio guardado en {path}")
            return path

        except Exception as e:
            logger.warning(f"[{session_id}] _download_audio_blob error: {e}")
            return None

    async def _download_image_blob(
        self, page, sender_name: str, session_id: str
    ) -> "Path | None":
        """
        Localiza el último mensaje de imagen en el chat abierto y descarga el blob.
        Retorna Path de un archivo temporal /tmp/pulpo_img_*.jpg, o None si falla.
        El caller es responsable de mover o eliminar el archivo.
        """
        import base64 as _b64
        import time
        from pathlib import Path

        try:
            _fetch_img_js = """
            async () => {
                const msgs = document.querySelectorAll('[data-testid="msg-container"]');
                for (let i = msgs.length - 1; i >= 0; i--) {
                    const img = msgs[i].querySelector('img[src^="blob:"]');
                    if (!img) continue;
                    try {
                        const resp = await fetch(img.src);
                        if (!resp.ok) continue;
                        const buf = await resp.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        let bin = '';
                        for (let b of bytes) bin += String.fromCharCode(b);
                        return btoa(bin);
                    } catch(e) { continue; }
                }
                return null;
            }
            """
            blob_b64 = None
            for _attempt in range(2):
                blob_b64 = await page.evaluate(_fetch_img_js)
                if blob_b64:
                    break
                if _attempt == 0:
                    logger.debug(f"[{session_id}] Imagen retry 2/2 para {sender_name}")
                    await asyncio.sleep(1.5)

            if not blob_b64:
                logger.debug(f"[{session_id}] _download_image_blob: sin blob para {sender_name}")
                return None

            path = Path(f"/tmp/pulpo_img_{int(time.time() * 1000)}.jpg")
            path.write_bytes(_b64.b64decode(blob_b64))
            logger.info(f"[{session_id}] Imagen guardada en {path}")
            return path

        except Exception as e:
            logger.warning(f"[{session_id}] _download_image_blob error: {e}")
            return None

    async def _download_audio_blob_at_index(
        self, page, session_id: str, raw_idx: int
    ) -> str | None:
        """
        Dado el índice de un elemento [data-pre-plain-text] en el DOM:
          1. Lo scrollea al centro del viewport (fuerza lazy-load del player)
          2. Espera hasta 3s a que aparezca el elemento <audio>
          3. Si hay blob URL, lo descarga; si no, clickea play y espera hasta 8s
          4. Retorna ruta a /tmp/pulpo_audio_*.ogg o None si falla

        Usa el mismo pipeline que _download_audio_blob pero opera sobre
        una posición concreta del DOM en lugar del "último audio del chat".
        """
        import time
        import base64 as _b64

        try:
            # Scroll al elemento para forzar que WA Web cargue el player de audio
            await page.evaluate(f"""
            () => {{
                const els = document.querySelectorAll('[data-pre-plain-text]');
                const el = els[{raw_idx}];
                if (el) el.scrollIntoView({{ block: 'center', behavior: 'instant' }});
            }}
            """)
            # Esperar hasta 3s a que aparezca el elemento <audio> en el DOM
            await page.wait_for_timeout(1500)

            blob_b64 = await page.evaluate(f"""
            async () => {{
                const tryFetch = async (audio) => {{
                    if (!audio.src || !audio.src.startsWith('blob:')) return null;
                    try {{
                        const resp = await fetch(audio.src);
                        const buf  = await resp.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        let bin = '';
                        for (let b of bytes) bin += String.fromCharCode(b);
                        return btoa(bin);
                    }} catch(e) {{ return null; }}
                }};

                const els = document.querySelectorAll('[data-pre-plain-text]');
                const el = els[{raw_idx}];
                if (!el) return null;

                const parent = el.parentElement || el;
                const audio = el.querySelector('audio') || parent.querySelector('audio');
                if (!audio) return null;

                // Intentar blob ya cargado
                let b64 = await tryFetch(audio);
                if (b64) return b64;

                // Blob no cargado: clickear play y esperar hasta 8s
                const playBtn = parent.querySelector(
                    'button[aria-label*="voz"], button[aria-label*="voice"], ' +
                    'button[aria-label*="Voice"], button[aria-label*="Reproducir"], ' +
                    'button[aria-label*="reproducir"], button[aria-label*="Escuchar"], ' +
                    '[data-icon="ptt-status"], [data-testid="audio-play"], [data-icon="audio-play"]'
                );
                if (playBtn) {{
                    playBtn.click();
                    await new Promise(resolve => {{
                        let elapsed = 0;
                        const iv = setInterval(() => {{
                            elapsed += 200;
                            if ((audio.src && audio.src.startsWith('blob:')) || elapsed >= 8000) {{
                                clearInterval(iv);
                                resolve();
                            }}
                        }}, 200);
                    }});
                    b64 = await tryFetch(audio);
                    if (b64) {{
                        audio.pause();
                        return b64;
                    }}
                }}
                return null;
            }}
            """)

            if not blob_b64:
                logger.debug(f"[{session_id}] _download_audio_blob_at_index[{raw_idx}]: sin blob")
                return None

            path = f"/tmp/pulpo_audio_{int(time.time() * 1000)}.ogg"
            with open(path, "wb") as f:
                f.write(_b64.b64decode(blob_b64))
            logger.info(f"[{session_id}] Audio histórico [{raw_idx}] guardado en {path}")
            return path

        except Exception as e:
            logger.warning(f"[{session_id}] _download_audio_blob_at_index[{raw_idx}] error: {e}")
            return None

    async def _download_audio_blob_by_preplain(
        self, page, session_id: str, pre_plain: str
    ) -> str | None:
        """
        Descarga el blob de un mensaje de voz buscando por el valor exacto del
        atributo data-pre-plain-text. Más robusto que _download_audio_blob_at_index
        porque no depende del índice DOM (que cambia con el virtual DOM de WA Web).
        """
        import time
        import base64 as _b64

        try:
            blob_b64 = None
            for _attempt in range(2):
              blob_b64 = await page.evaluate("""
              async (prePlain) => {
                const tryFetch = async (audio) => {
                    if (!audio || !audio.src || !audio.src.startsWith('blob:')) return null;
                    try {
                        const resp = await fetch(audio.src);
                        const buf = await resp.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        let bin = '';
                        for (let b of bytes) bin += String.fromCharCode(b);
                        return btoa(bin);
                    } catch(e) { return null; }
                };

                // Buscar el elemento por valor exacto de data-pre-plain-text
                let el = null;
                for (const e of document.querySelectorAll('[data-pre-plain-text]')) {
                    if (e.getAttribute('data-pre-plain-text') === prePlain) { el = e; break; }
                }
                if (!el) return null;

                // Scroll al elemento para que WA cargue el player de audio
                el.scrollIntoView({ block: 'center', behavior: 'instant' });
                await new Promise(r => setTimeout(r, 1800));

                const parent = el.parentElement || el;
                let audio = el.querySelector('audio') || parent.querySelector('audio');

                // Si no hay audio blob todavía, buscar el botón play y clickear
                if (!audio || !audio.src?.startsWith('blob:')) {
                    const playBtn = parent.querySelector(
                        'button[aria-label*="voz"], button[aria-label*="voice"], ' +
                        'button[aria-label*="Reproducir"], button[aria-label*="reproducir"], ' +
                        'button[aria-label*="Escuchar"], [data-icon="ptt-status"]'
                    );
                    if (playBtn) {
                        playBtn.click();
                        await new Promise(resolve => {
                            let elapsed = 0;
                            const iv = setInterval(() => {
                                elapsed += 200;
                                audio = el.querySelector('audio') || parent.querySelector('audio');
                                if ((audio?.src?.startsWith('blob:')) || elapsed >= 8000) {
                                    clearInterval(iv); resolve();
                                }
                            }, 200);
                        });
                    } else if (!audio) {
                        return null;
                    }
                }

                const b64 = await tryFetch(audio);
                if (b64) {
                    try { audio.pause(); } catch(e) {}
                    return b64;
                }
                return null;
            }
              """, pre_plain)
              if blob_b64:
                  break
              if _attempt == 0:
                  logger.debug(f"[{session_id}] Audio preplain retry 2/2 para '{pre_plain[:40]}'")
                  await asyncio.sleep(1.5)

            if not blob_b64:
                logger.debug(f"[{session_id}] _download_audio_blob_by_preplain: sin blob para '{pre_plain[:50]}'")
                return None

            path = f"/tmp/pulpo_audio_{int(time.time() * 1000)}.ogg"
            with open(path, "wb") as f:
                f.write(_b64.b64decode(blob_b64))
            logger.info(f"[{session_id}] Audio (preplain) guardado en {path}")
            return path

        except Exception as e:
            logger.warning(f"[{session_id}] _download_audio_blob_by_preplain error: {e}")
            return None

    async def _fetch_audio_idb_keys(self, page, session_id: str) -> list[dict]:
        """
        Lee todos los mensajes PTT/audio del IndexedDB de WA Web.
        Retorna lista de {t, mediaKey, directPath, duration, type}.
        Fallback para cuando el blob DOM no está disponible (audio histórico).
        """
        js = """
        () => new Promise((resolve) => {
            const toB64 = (buf) => {
                if (typeof buf === 'string') return buf;
                const bytes = new Uint8Array(buf instanceof ArrayBuffer ? buf : buf.buffer || buf);
                let s = '';
                for (let i = 0; i < bytes.byteLength; i++) s += String.fromCharCode(bytes[i]);
                return btoa(s);
            };

            const tryRead = (dbName) => new Promise((res) => {
                const req = indexedDB.open(dbName);
                req.onerror = () => res([]);
                req.onsuccess = (e) => {
                    const db = e.target.result;
                    const storeNames = Array.from(db.objectStoreNames);
                    const msgStore = storeNames.find(s => s === 'message' || s === 'msg' || s === 'messages');
                    if (!msgStore) { db.close(); res([]); return; }
                    const tx = db.transaction([msgStore], 'readonly');
                    const store = tx.objectStore(msgStore);
                    const results = [];
                    store.openCursor().onsuccess = (e) => {
                        const cursor = e.target.result;
                        if (cursor) {
                            const msg = cursor.value;
                            if (msg && msg.mediaKey && msg.directPath &&
                                (msg.type === 'ptt' || msg.type === 'audio')) {
                                try {
                                    // WA Web puede almacenar t en milisegundos; normalizar a segundos
                                    const tSec = msg.t > 1e10 ? Math.floor(msg.t / 1000) : msg.t;
                                    results.push({
                                        t: tSec,
                                        mediaKey: toB64(msg.mediaKey),
                                        directPath: msg.directPath,
                                        duration: msg.duration || 0,
                                        type: msg.type,
                                    });
                                } catch (_) {}
                            }
                            cursor.continue();
                        } else {
                            db.close();
                            res(results);
                        }
                    };
                    tx.onerror = () => { db.close(); res([]); };
                };
            });

            (async () => {
                let candidates = ['model-storage', 'wawc', 'wa-1', 'wawcV2', 'hammerhead'];
                try {
                    const dbs = await indexedDB.databases();
                    const found = dbs.map(d => d.name).filter(Boolean);
                    candidates = [...new Set([...found, ...candidates])];
                } catch(_) {}

                for (const name of candidates) {
                    const r = await tryRead(name);
                    if (r.length > 0) { resolve(r); return; }
                }
                resolve([]);
            })();
        })
        """
        try:
            keys = await page.evaluate(js)
            logger.info(f"[{session_id}] IDB: {len(keys)} mensajes PTT/audio encontrados")
            return keys
        except Exception as e:
            logger.warning(f"[{session_id}] IDB read error: {e}")
            return []

    async def _download_decrypt_audio_cdn(
        self, direct_path: str, media_key_b64: str, session_id: str
    ) -> str | None:
        """
        Descarga y descifra un audio PTT de WA vía CDN usando directPath + mediaKey del IDB.
        Fallback cuando el blob DOM no está disponible.
        """
        import time as _time
        try:
            from tools.wa_decrypt import download_and_decrypt
            path = f"/tmp/pulpo_audio_{int(_time.time() * 1000)}.ogg"
            await download_and_decrypt(direct_path, media_key_b64, path)
            logger.info(f"[{session_id}] CDN decrypt OK → {path}")
            return path
        except Exception as e:
            logger.warning(f"[{session_id}] CDN decrypt fallido: {e}")
            return None

    async def _install_blob_interceptor(self, page) -> None:
        """
        Inyecta un interceptor de URL.createObjectURL en la página para capturar
        blobs de audio (PTT) en el momento exacto que WA Web los crea.
        Los blobs capturados se acumulan en window.__capturedAudioBlobsB64 como base64.
        Solo se instala una vez por página.
        """
        await page.evaluate("""
        () => {
            if (window.__blobInterceptorInstalled) return;
            window.__blobInterceptorInstalled = true;
            window.__capturedAudioBlobsB64 = [];
            const _orig = URL.createObjectURL.bind(URL);
            URL.createObjectURL = function(obj) {
                const url = _orig(obj);
                // Capturar solo Blobs de audio (PTT) — típicamente ogg/opus, >1KB
                if (obj instanceof Blob && obj.size > 500 &&
                    (obj.type.includes('audio') || obj.type.includes('ogg') || obj.type === '')) {
                    const reader = new FileReader();
                    reader.readAsDataURL(obj);
                    reader.onloadend = () => {
                        const b64 = reader.result.split(',')[1];
                        if (b64) window.__capturedAudioBlobsB64.push(b64);
                    };
                }
                return url;
            };
        }
        """)

    async def _download_visible_ptt_blob(
        self, page, session_id: str, prePlain_key: str
    ) -> str | None:
        """
        Descarga el blob de un PTT clickeando su botón play.
        Usa el interceptor de URL.createObjectURL para capturar el blob
        en el momento exacto que WA Web lo crea (evita race conditions).
        """
        import base64 as _b64
        import time as _time

        try:
            # Encontrar el contenedor PTT por key, scrollear, y hacer click play
            found = await page.evaluate("""
            (prePlainKey) => {
                const buildKey = (c) => {
                    let msgTime = '';
                    const w = document.createTreeWalker(c, NodeFilter.SHOW_TEXT, null);
                    let n;
                    while (n = w.nextNode()) {
                        const t = n.textContent.trim();
                        if (/^\d{1,2}:\d{2}(\s*(a|p)[\.\s]*m\.?)?$/i.test(t)) msgTime = t;
                    }
                    let msgDate = '';
                    let anc = c.parentElement;
                    for (let j = 0; j < 12 && anc; j++) {
                        const pp = anc.querySelector('[data-pre-plain-text]');
                        if (pp) {
                            const m = pp.getAttribute('data-pre-plain-text').match(/(\d{1,2}\/\d{1,2}\/\d{4})/);
                            if (m) { msgDate = m[1]; break; }
                        }
                        anc = anc.parentElement;
                    }
                    const timeText = (msgTime && msgDate) ? msgTime + ', ' + msgDate : msgTime;
                    const sEl = c.querySelector('span[aria-label$=":"]');
                    const sender = sEl ? (sEl.getAttribute('aria-label') || '').replace(/:$/, '').trim() : '';
                    return '[' + timeText + '] ' + (sender ? sender + ': ' : '');
                };

                // Solo buscar ptt-status (no reproduciendo aún) para evitar toggle play/stop
                for (const ptt of document.querySelectorAll('[data-icon="ptt-status"]')) {
                    let c = ptt;
                    for (let i=0;i<15;i++){if(!c.parentElement)break;c=c.parentElement;if(c.classList.contains('message-in')||c.classList.contains('message-out'))break;}
                    if (buildKey(c) !== prePlainKey) continue;

                    const btn = c.querySelector(
                        'button[aria-label*="voz"],button[aria-label*="voice"],' +
                        'button[aria-label*="Reproducir"],button[aria-label*="reproducir"],' +
                        'button[aria-label*="Escuchar"]'
                    ) || ptt.closest('button') || ptt.parentElement?.querySelector('button');

                    if (!btn) return 'noBtn';

                    // Limpiar cola de blobs previos y scrollear
                    if (window.__capturedAudioBlobsB64) window.__capturedAudioBlobsB64 = [];
                    btn.scrollIntoView({ block: 'center', behavior: 'instant' });
                    btn.click();
                    return 'clicked';
                }
                return null;
            }
            """, prePlain_key)

            if not found:
                logger.debug(f"[{session_id}] ptt_blob: no encontrado '{prePlain_key[:50]}'")
                return None
            if found == "noBtn":
                logger.debug(f"[{session_id}] ptt_blob: sin botón play para '{prePlain_key[:50]}'")
                return None

            # Esperar a que el interceptor capture el blob (hasta 30s)
            # También intentar fetch directo del blob URL del elemento <audio>
            blob_b64 = None
            for _ in range(150):
                await page.wait_for_timeout(200)
                # Método 1: interceptor URL.createObjectURL
                blob_b64 = await page.evaluate(
                    "() => window.__capturedAudioBlobsB64?.shift() || null"
                )
                if blob_b64:
                    logger.debug(f"[{session_id}] ptt_blob: capturado via interceptor")
                    break
                # Método 2: fetch directo del blob URL en el elemento <audio>
                blob_b64 = await page.evaluate("""
                async () => {
                    const audio = document.querySelector('audio[src^="blob:"]');
                    if (!audio) return null;
                    try {
                        const resp = await fetch(audio.src);
                        if (!resp.ok) return null;
                        const blob = await resp.blob();
                        if (blob.size < 500) return null;
                        return await new Promise(resolve => {
                            const reader = new FileReader();
                            reader.readAsDataURL(blob);
                            reader.onloadend = () => resolve(reader.result ? reader.result.split(',')[1] : null);
                        });
                    } catch(e) { return null; }
                }
                """)
                if blob_b64:
                    logger.debug(f"[{session_id}] ptt_blob: capturado via audio.src fetch")
                    break

            if not blob_b64:
                logger.info(f"[{session_id}] ptt_blob: no capturado en 30s para '{prePlain_key[:50]}'")
                # Parar el audio si está reproduciendo
                await page.evaluate("""
                () => { try { document.querySelector('audio')?.pause(); } catch(e) {} }
                """)
                return None

            # Parar el audio
            await page.evaluate("""
            () => { try { document.querySelector('audio')?.pause(); } catch(e) {} }
            """)

            path = f"/tmp/pulpo_audio_{int(_time.time() * 1000)}.ogg"
            with open(path, "wb") as f:
                f.write(_b64.b64decode(blob_b64))
            logger.info(f"[{session_id}] PTT blob capturado: {path}")
            return path

        except Exception as e:
            logger.warning(f"[{session_id}] _download_visible_ptt_blob error: {e}")
            return None

    async def _download_document_from_page(self, page, filename: str, save_path: Path) -> bool:
        """
        Descarga un documento de WA Web haciendo click en su botón Descargar.
        Dedup por existencia del archivo en disco. Retorna True si descargó o ya existía.
        """
        if save_path.exists():
            return True
        save_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with page.expect_download(timeout=20_000) as dl_info:
                clicked = await page.evaluate("""(fn) => {
                    const btn = [...document.querySelectorAll('div[role="button"][title]')]
                        .find(b => b.title.includes(fn));
                    if (btn) { btn.click(); return true; }
                    return false;
                }""", filename)
            if not clicked:
                logger.debug(f"[doc] Botón no encontrado en DOM para '{filename}'")
                return False
            dl = await dl_info.value
            await dl.save_as(str(save_path))
            logger.info(f"[doc] Descargado: {save_path}")
            return True
        except Exception as e:
            logger.warning(f"[doc] Error descargando '{filename}': {e}")
            return False

    # ------------------------------------------------------------------
    # Scraping histórico
    # ------------------------------------------------------------------

    async def scrape_full_history(
        self, session_id: str, contact_name: str, scroll_rounds: int = 50,
        doc_save_dir: "Path | None" = None,
        from_date: "date | None" = None,
    ) -> list[dict]:
        """
        Abre el chat del contacto/grupo en WA Web, hace scroll hacia arriba
        para cargar mensajes históricos, y extrae todos los mensajes visibles.

        Retorna lista de dicts: {timestamp, sender, body, is_outbound}
        - timestamp: ISO string 'YYYY-MM-DD HH:MM:SS' si disponible, None si solo tiene hora de hoy
        - sender: nombre del remitente en grupos, None en chats individuales
        - body: texto del mensaje (o '[audio]', '[media]')
        - is_outbound: bool
        """
        import re
        from datetime import datetime, date

        page = self.get_page(session_id)
        if not page:
            return []

        try:
            # 1. Abrir el chat en el sidebar
            # WA Web usa non-breaking spaces (\u00a0) en los títulos — comparamos
            # normalizando espacios para evitar fallos de encoding.
            def _normalize(s: str) -> str:
                import unicodedata
                return unicodedata.normalize("NFKC", s).strip()

            # Usar evaluate_handle para obtener el elemento DOM y luego
            # click() real de Playwright (genera eventos de mouse que React entiende).
            row_handle = await page.evaluate_handle(
                """(target) => {
                    const norm = s => s.replace(/[\\u00a0\\u202a\\u202c\\u200e\\u200f]/g, ' ').trim();
                    const grid = document.querySelector('[role="grid"]');
                    if (!grid) return null;
                    for (const s of grid.querySelectorAll('span[title]')) {
                        if (norm(s.getAttribute('title')) === norm(target)) {
                            return s.closest('[role="row"]') || s.closest('[data-id]') || s;
                        }
                    }
                    return null;
                }""",
                _normalize(contact_name),
            )
            if not row_handle or await row_handle.evaluate("el => el === null"):
                logger.warning(f"[{session_id}] scrape_full_history: no encontré '{contact_name}' en el sidebar")
                return []
            await row_handle.scroll_into_view_if_needed()
            await row_handle.click()
            await page.wait_for_timeout(2000)

            # Instalar interceptor de blobs de audio antes de iniciar el scroll
            await self._install_blob_interceptor(page)

            # 2. Scroll hacia arriba hasta que no aparezcan mensajes nuevos
            # WA Web carga más mensajes cuando llegás al tope del panel
            prev_count = 0
            stale_rounds = 0
            for _ in range(scroll_rounds):
                await page.evaluate("""
                () => {
                    // Buscar el contenedor scrolleable del panel de mensajes
                    const candidates = [
                        document.querySelector('[data-testid="conversation-panel-messages"]'),
                        document.querySelector('#main [tabindex="-1"]'),
                        document.querySelector('#main [style*="overflow"]'),
                        ...document.querySelectorAll('#main div'),
                    ];
                    for (const el of candidates) {
                        if (el && el.scrollHeight > el.clientHeight && el.scrollTop > 0) {
                            el.scrollTop = 0;
                            return;
                        }
                    }
                    // Fallback: scrollear el primer div con overflow en #main
                    const main = document.querySelector('#main');
                    if (main) main.scrollTop = 0;
                }
                """)
                await page.wait_for_timeout(900)
                # Usar el selector correcto (div, no span)
                cur_count = await page.evaluate(
                    "() => document.querySelectorAll('[data-pre-plain-text]').length"
                )
                if cur_count == prev_count:
                    stale_rounds += 1
                    if stale_rounds >= 3:
                        break
                else:
                    stale_rounds = 0
                prev_count = cur_count
            logger.info(f"[{session_id}] scrape '{contact_name}': {prev_count} msgs en DOM tras scroll")

            # 3. Extraer PARTE A: mensajes de texto (data-pre-plain-text).
            # DEBE ocurrir aquí, con el DOM al tope (mensajes históricos cargados).
            # Después del scroll hacia adelante WA Web virtualiza y borra estos nodos.
            def _extract_text_msgs_js():
                return """
                () => {
                    const msgs = [];
                    const textEls = document.querySelectorAll('[data-pre-plain-text]');
                    for (let idx = 0; idx < textEls.length; idx++) {
                        const el = textEls[idx];
                        const prePlain = el.getAttribute('data-pre-plain-text') || '';
                        // Estructura reply: primer hijo = bloque citado, último hijo = mensaje real
                        // Si hay un solo hijo directo, es un mensaje normal (sin reply)
                        const children = [...el.children];
                        let body = '';
                        let quotedBody = '';
                        if (children.length >= 2) {
                            // Mensaje con reply: el mensaje real está en el último hijo
                            const realEl = children[children.length - 1].querySelector('span.copyable-text, [data-testid="selectable-text"]');
                            body = realEl ? realEl.innerText.trim() : '';
                            // El bloque citado está en el primer hijo
                            const qb = children[0];
                            const quotedText = qb.querySelector('span.copyable-text, [data-testid="selectable-text"]');
                            quotedBody = quotedText ? quotedText.innerText.trim() : '';
                            if (quotedBody) {
                                // Capturar sender del mensaje citado
                                let quotedSender = '';
                                const qsAuthor = qb.querySelector('[data-testid="author"]');
                                const qsColor  = qb.querySelector('span[style*="color:#"], span[style*="color: #"]');
                                const qsDir    = qb.querySelector('span[dir="ltr"]:not(.copyable-text), span[dir="auto"]:not(.copyable-text)');
                                if (qsAuthor) quotedSender = qsAuthor.innerText.trim();
                                else if (qsColor) quotedSender = qsColor.innerText.trim();
                                else if (qsDir) {
                                    const t = qsDir.innerText.trim();
                                    if (t && t.length < 60 && t !== quotedBody) quotedSender = t;
                                }
                                const replyMeta = quotedSender ? '[' + quotedSender + '] ' : '';
                                body = body + '\\n> ↩ ' + replyMeta + quotedBody;
                            }
                        } else {
                            const textEl = el.querySelector('span.copyable-text, [data-testid="msg-text"]');
                            body = textEl ? textEl.innerText.trim() : '';
                        }
                        const parent = el.parentElement || el;
                        const hasAudio = !!el.querySelector('audio, [data-testid^="audio"]')
                                      || !!parent.querySelector('audio, [data-testid^="audio"]')
                                      || !!parent.querySelector('[data-icon="audio-play"], [data-icon="ptt-play"], [data-icon="ptt-status"], [data-icon="media-play"]');
                        const isOut = !!el.closest('.message-out')
                                   || !!el.querySelector('[data-icon^="msg-dblcheck"], [data-icon="msg-check"], [data-icon="msg-time"]');
                        const effectiveBody = hasAudio ? '[audio]' : (body || '[media]');
                        msgs.push({ source: 'text', idx, prePlain, body: effectiveBody, isOut });
                    }
                    return msgs;
                }
                """

            def _extract_audio_msgs_js():
                """Busca mensajes de voz que NO usan data-pre-plain-text.
                Selectores confirmados inspeccionando DOM real de WA Web (es-AR):
                  - [data-icon="ptt-status"]  → ícono dentro del player PTT
                  - button[aria-label*="voz"] → botón play (locale es-AR)
                  - button[aria-label*="voice"] → botón play (locale en)
                """
                return """
                    const msgs = [];
                    const seen = new Set();
                    // Combinar todos los posibles indicadores de audio/PTT
                    const indSet = new Set();
                    for (const el of document.querySelectorAll(
                        '[data-icon="ptt-status"], [data-icon="media-play"], ' +
                        'button[aria-label*="voz"], button[aria-label*="voice"], ' +
                        'button[aria-label*="Voice"], button[aria-label*="audio"], ' +
                        '[data-icon="ptt-play"], [data-icon="audio-play"], audio'
                    )) { indSet.add(el); }
                    const audioIndicators = [...indSet];
                    for (const indicator of audioIndicators) {
                        let msgContainer = indicator;
                        for (let i = 0; i < 15; i++) {
                            if (!msgContainer.parentElement) break;
                            msgContainer = msgContainer.parentElement;
                            if (msgContainer.getAttribute('role') === 'row' ||
                                msgContainer.classList.contains('message-in') ||
                                msgContainer.classList.contains('message-out')) break;
                        }
                        // Saltar si tiene data-pre-plain-text: ya fue capturado por Part A
                        if (msgContainer.querySelector('[data-pre-plain-text]')) continue;

                        // Timestamp — WA Web ya no usa data-testid="msg-meta" en PTT.
                        // Estrategia: (1) último text-node que parece hora en el contenedor,
                        //             (2) fecha del data-pre-plain-text más cercano en DOM.
                        let msgTime = '';
                        const walker = document.createTreeWalker(msgContainer, NodeFilter.SHOW_TEXT, null);
                        let node2;
                        while (node2 = walker.nextNode()) {
                            const t = node2.textContent.trim();
                            // Horas con a.m./p.m. (formato 12h) o 2 dígitos HH:MM (formato 24h)
                            if (/^\d{1,2}:\d{2}(\s*(a|p)[\.\s]*m\.?)?$/i.test(t)) msgTime = t;
                        }

                        let msgDate = '';
                        // Estrategia de fecha en dos pasos:
                        // 1) Último data-pre-plain-text con fecha antes del audio
                        // 2) Separador de día WA (SPAN con "martes", "ayer", "17 de marzo…")
                        //    que aparezca DESPUÉS del último PP y ANTES del audio.
                        //    WA usa nombres de día (lunes…domingo / hoy / ayer) para la semana
                        //    actual y fecha completa para semanas anteriores.
                        const _monthES = {
                            'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,
                            'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12
                        };
                        // JS getDay(): 0=Dom,1=Lun,2=Mar,3=Mié,4=Jue,5=Vie,6=Sáb
                        const _dayES = {
                            'domingo':0,'lunes':1,'martes':2,
                            'miercoles':3,'miércoles':3,'jueves':4,'viernes':5,
                            'sabado':6,'sábado':6
                        };
                        // Paso 1: último data-pre-plain-text con fecha antes del audio
                        let lastPPEl = null;
                        for (const el of document.querySelectorAll('[data-pre-plain-text]')) {
                            if (!(msgContainer.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) break;
                            const m = el.getAttribute('data-pre-plain-text').match(/(\d{1,2}\/\d{1,2}\/\d{4})/);
                            if (m) { lastPPEl = el; msgDate = m[1]; }
                        }
                        // Paso 2: buscar separador de día WA entre lastPPEl y el audio
                        const _today = new Date();
                        for (const el of document.querySelectorAll('span')) {
                            // solo elementos que vienen DESPUÉS de lastPPEl en el DOM
                            if (lastPPEl && !(lastPPEl.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
                            // parar cuando lleguemos al audio
                            if (!(msgContainer.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) break;
                            // texto directo del span (no descendientes) — los separadores son nodos texto simples
                            const ownTxt = [...el.childNodes]
                                .filter(n => n.nodeType === 3)
                                .map(n => n.textContent.trim()).join('').trim();
                            if (!ownTxt || ownTxt.length > 60) continue;
                            const low = ownTxt.toLowerCase()
                                .replace(/\u00e9/g,'e').replace(/\u00e1/g,'a')
                                .replace(/\u00f3/g,'o').replace(/\u00fa/g,'u');
                            let sepDate = null;
                            // Fecha completa "17 de marzo de 2026"
                            const fd = ownTxt.match(/(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})/i);
                            if (fd) {
                                const d=parseInt(fd[1]), mo=_monthES[fd[2].toLowerCase()]||0, y=parseInt(fd[3]);
                                if (mo) sepDate = d+'/'+mo+'/'+y;
                            } else if (low === 'hoy') {
                                sepDate = _today.getDate()+'/'+(_today.getMonth()+1)+'/'+_today.getFullYear();
                            } else if (low === 'ayer') {
                                const d2 = new Date(_today); d2.setDate(d2.getDate()-1);
                                sepDate = d2.getDate()+'/'+( d2.getMonth()+1)+'/'+d2.getFullYear();
                            } else if (_dayES[low] !== undefined) {
                                // Nombre de día: encontrar la ocurrencia más reciente antes de hoy
                                const target = _dayES[low];
                                let ago = (_today.getDay() - target + 7) % 7;
                                if (ago === 0) ago = 7; // mismo día de semana = semana pasada
                                const d3 = new Date(_today); d3.setDate(d3.getDate() - ago);
                                sepDate = d3.getDate()+'/'+( d3.getMonth()+1)+'/'+d3.getFullYear();
                            }
                            if (sepDate) { msgDate = sepDate; break; }
                        }

                        let timeText = '';
                        if (msgTime && msgDate)       timeText = msgTime + ', ' + msgDate;
                        else if (msgTime)              timeText = msgTime;
                        if (!timeText) continue;

                        // Sender: priorizar data-testid="author", luego aria-label, luego color,
                        // luego el span de nombre en grupos PTT (._ak4h span / span._ao3e[dir])
                        const senderTestEl = msgContainer.querySelector('[data-testid="author"]');
                        const senderAriaEl = msgContainer.querySelector('span[aria-label$=":"]');
                        const senderColorEl = msgContainer.querySelector('span[style*="color:#"], span[style*="color: #"]');
                        const senderHeaderEl = msgContainer.querySelector('._ak4h span[dir="auto"]');
                        let sender = '';
                        if (senderTestEl) {
                            sender = senderTestEl.innerText.trim();
                        } else if (senderAriaEl) {
                            sender = (senderAriaEl.getAttribute('aria-label') || '').replace(/:$/, '').trim();
                        } else if (senderColorEl) {
                            sender = senderColorEl.innerText.trim();
                        } else if (senderHeaderEl) {
                            sender = senderHeaderEl.innerText.trim();
                        }

                        // Dedup por (timeText, sender)
                        const key = timeText + '|' + sender;
                        if (seen.has(key)) continue;
                        seen.add(key);

                        const isOut = !!msgContainer.closest('.message-out') ||
                                      msgContainer.classList.contains('message-out');
                        const prePlain = '[' + timeText + '] ' + (sender ? sender + ': ' : '');
                        msgs.push({ source: 'audio', idx: -1, prePlain, body: '[audio]', isOut, msgTime, msgDate, sender });
                    }
                    return msgs;
                """

            def _extract_document_msgs_js():
                """Busca mensajes de documento que NO usan data-pre-plain-text.
                Selector confirmado inspeccionando DOM real de WA Web:
                  - div[role="button"][title^="Descargar"] → botón de descarga del doc
                  - title: 'Descargar "nombre.ext"'
                  - innerText: 'EXT\\nnombre.ext\\nEXT•tamaño'
                """
                return """
                () => {
                    const msgs = [];
                    const seen = new Set();
                    const _monthES = {
                        'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,
                        'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12
                    };
                    const _dayES = {
                        'domingo':0,'lunes':1,'martes':2,
                        'miercoles':3,'miércoles':3,'jueves':4,'viernes':5,
                        'sabado':6,'sábado':6
                    };
                    const _today = new Date();

                    for (const docBtn of document.querySelectorAll('div[role="button"][title^="Descargar"]')) {
                        // Subir al contenedor del mensaje
                        let msgContainer = docBtn;
                        for (let i = 0; i < 15; i++) {
                            if (!msgContainer.parentElement) break;
                            msgContainer = msgContainer.parentElement;
                            if (msgContainer.classList.contains('message-in') ||
                                msgContainer.classList.contains('message-out')) break;
                        }

                        // Filename del title: 'Descargar "archivo.ext"'
                        const filename = docBtn.title.replace(/^Descargar\s*"?/, '').replace(/"$/, '').trim();
                        if (!filename) continue;

                        // Tamaño del innerText (3 líneas): EXT / nombre.ext / EXT•3 kB
                        const innerParts = (docBtn.innerText || '').split('\\n');
                        const sizeLine = innerParts[2] || '';
                        const sizeMatch = sizeLine.match(/•\s*([\d.,]+\s*[kKmMgG]?[bB])/);
                        const size = sizeMatch ? sizeMatch[1].trim() : '';
                        const ext = filename.split('.').pop().toUpperCase();

                        // Timestamp — caminar nodos de texto buscando hora
                        let msgTime = '';
                        const walker = document.createTreeWalker(msgContainer, NodeFilter.SHOW_TEXT, null);
                        let node2;
                        while (node2 = walker.nextNode()) {
                            const t = node2.textContent.trim();
                            if (/^\d{1,2}:\d{2}(\s*(a|p)[\.\s]*m\.?)?$/i.test(t)) msgTime = t;
                        }
                        if (!msgTime) continue;

                        // Fecha — igual que Part B: último data-pre-plain-text antes del doc,
                        // luego separadores de día WA (hoy / ayer / nombre de día / fecha completa)
                        let msgDate = '';
                        let lastPPEl = null;
                        for (const el of document.querySelectorAll('[data-pre-plain-text]')) {
                            if (!(msgContainer.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) break;
                            const m = el.getAttribute('data-pre-plain-text').match(/(\d{1,2}\/\d{1,2}\/\d{4})/);
                            if (m) { lastPPEl = el; msgDate = m[1]; }
                        }
                        for (const el of document.querySelectorAll('span')) {
                            if (lastPPEl && !(lastPPEl.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
                            if (!(msgContainer.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) break;
                            const ownTxt = [...el.childNodes]
                                .filter(n => n.nodeType === 3)
                                .map(n => n.textContent.trim()).join('').trim();
                            if (!ownTxt || ownTxt.length > 60) continue;
                            const low = ownTxt.toLowerCase()
                                .replace(/\u00e9/g,'e').replace(/\u00e1/g,'a')
                                .replace(/\u00f3/g,'o').replace(/\u00fa/g,'u');
                            let sepDate = null;
                            const fd = ownTxt.match(/(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})/i);
                            if (fd) {
                                const d=parseInt(fd[1]), mo=_monthES[fd[2].toLowerCase()]||0, y=parseInt(fd[3]);
                                if (mo) sepDate = d+'/'+mo+'/'+y;
                            } else if (low === 'hoy') {
                                sepDate = _today.getDate()+'/'+(_today.getMonth()+1)+'/'+_today.getFullYear();
                            } else if (low === 'ayer') {
                                const d2 = new Date(_today); d2.setDate(d2.getDate()-1);
                                sepDate = d2.getDate()+'/'+( d2.getMonth()+1)+'/'+d2.getFullYear();
                            } else if (_dayES[low] !== undefined) {
                                const target = _dayES[low];
                                let ago = (_today.getDay() - target + 7) % 7;
                                if (ago === 0) ago = 7;
                                const d3 = new Date(_today); d3.setDate(d3.getDate() - ago);
                                sepDate = d3.getDate()+'/'+( d3.getMonth()+1)+'/'+d3.getFullYear();
                            }
                            if (sepDate) { msgDate = sepDate; break; }
                        }

                        let timeText = '';
                        if (msgTime && msgDate)  timeText = msgTime + ', ' + msgDate;
                        else if (msgTime)         timeText = msgTime;
                        if (!timeText) continue;

                        // Sender (grupos)
                        const senderColorEl = msgContainer.querySelector('span[style*="color:#"], span[style*="color: #"]');
                        const senderAriaEl  = msgContainer.querySelector('span[aria-label$=":"]');
                        let sender = '';
                        if (senderColorEl) sender = senderColorEl.innerText.trim();
                        else if (senderAriaEl) sender = (senderAriaEl.getAttribute('aria-label') || '').replace(/:$/, '').trim();

                        const isOut = msgContainer.classList.contains('message-out');
                        const body = size ? '`' + filename + '` (' + ext + ' · ' + size + ')' : '`' + filename + '`';
                        const prePlain = '[' + timeText + '] ' + (sender ? sender + ': ' : '');
                        const key = prePlain + '|' + filename;
                        if (seen.has(key)) continue;
                        seen.add(key);

                        msgs.push({ source: 'document', idx: -1, prePlain, body, isOut, msg_type: 'document' });
                    }
                    return msgs;
                }
                """

            def _extract_image_msgs_js():
                """Busca mensajes de imagen sin caption (sin data-pre-plain-text).
                Las imágenes CON caption ya las captura _extract_text_msgs_js como texto.
                Descarga el blob inline (async) y devuelve blobB64 + imgSrc para retry en Python.
                """
                return """
                async () => {
                    const msgs = [];
                    const seen = new Set();
                    const _monthES = {
                        'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,
                        'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12
                    };
                    const _dayES = {
                        'domingo':0,'lunes':1,'martes':2,
                        'miercoles':3,'miércoles':3,'jueves':4,'viernes':5,
                        'sabado':6,'sábado':6
                    };
                    const _today = new Date();

                    // Imágenes sin caption: no tienen data-pre-plain-text en su contenedor
                    // Solo procesar elementos en el viewport actual para evitar re-detección de
                    // mensajes viejos que siguen en el DOM mientras se scrollea a fechas más recientes.
                    const allMsgContainers = [...document.querySelectorAll('.message-in, .message-out')]
                        .filter(m => {
                            const r = m.getBoundingClientRect();
                            return r.bottom > -200 && r.top < window.innerHeight + 200;
                        });
                    for (const msgContainer of allMsgContainers) {
                        if (msgContainer.querySelector('[data-pre-plain-text]')) continue;
                        const imgEl = msgContainer.querySelector('img[src^="blob:"]');
                        if (!imgEl) continue;

                        // Timestamp
                        let msgTime = '';
                        const walker = document.createTreeWalker(msgContainer, NodeFilter.SHOW_TEXT, null);
                        let node;
                        while (node = walker.nextNode()) {
                            const t = node.textContent.trim();
                            if (/^\\d{1,2}:\\d{2}(\\s*(a|p)[\\.\\s]*m\\.?)?$/i.test(t)) msgTime = t;
                        }
                        if (!msgTime) continue;

                        // Fecha
                        let msgDate = '';
                        let lastPPEl = null;
                        for (const el of document.querySelectorAll('[data-pre-plain-text]')) {
                            if (!(msgContainer.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) break;
                            const m = el.getAttribute('data-pre-plain-text').match(/(\\d{1,2}\\/\\d{1,2}\\/\\d{4})/);
                            if (m) { lastPPEl = el; msgDate = m[1]; }
                        }
                        for (const el of document.querySelectorAll('span')) {
                            if (lastPPEl && !(lastPPEl.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
                            if (!(msgContainer.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) break;
                            const ownTxt = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('').trim();
                            if (!ownTxt || ownTxt.length > 60) continue;
                            const low = ownTxt.toLowerCase()
                                .replace(/\\u00e9/g,'e').replace(/\\u00e1/g,'a')
                                .replace(/\\u00f3/g,'o').replace(/\\u00fa/g,'u');
                            let sepDate = null;
                            const fd = ownTxt.match(/(\\d{1,2})\\s+de\\s+(\\w+)\\s+de\\s+(\\d{4})/i);
                            if (fd) {
                                const d=parseInt(fd[1]), mo=_monthES[fd[2].toLowerCase()]||0, y=parseInt(fd[3]);
                                if (mo) sepDate = d+'/'+mo+'/'+y;
                            } else if (low === 'hoy') {
                                sepDate = _today.getDate()+'/'+(_today.getMonth()+1)+'/'+_today.getFullYear();
                            } else if (low === 'ayer') {
                                const d2 = new Date(_today); d2.setDate(d2.getDate()-1);
                                sepDate = d2.getDate()+'/'+(d2.getMonth()+1)+'/'+d2.getFullYear();
                            } else if (_dayES[low] !== undefined) {
                                const target = _dayES[low];
                                let ago = (_today.getDay() - target + 7) % 7;
                                if (ago === 0) ago = 7;
                                const d3 = new Date(_today); d3.setDate(d3.getDate() - ago);
                                sepDate = d3.getDate()+'/'+(d3.getMonth()+1)+'/'+d3.getFullYear();
                            }
                            if (sepDate) { msgDate = sepDate; break; }
                        }

                        const timeText = msgTime && msgDate ? msgTime + ', ' + msgDate : msgTime;
                        if (!timeText) continue;

                        const isOut = msgContainer.classList.contains('message-out');
                        const prePlain = '[' + timeText + '] ';
                        const key = prePlain + '|img';
                        if (seen.has(key)) continue;
                        seen.add(key);

                        // Intentar descargar el blob inline mientras el elemento está visible
                        let blobB64 = null;
                        const imgSrc = imgEl.src;
                        try {
                            const resp = await fetch(imgEl.src);
                            if (resp.ok) {
                                const buf = await resp.arrayBuffer();
                                const bytes = new Uint8Array(buf);
                                let bin = '';
                                for (let b of bytes) bin += String.fromCharCode(b);
                                blobB64 = btoa(bin);
                            }
                        } catch(e) {}

                        msgs.push({ source: 'image', idx: -1, prePlain, body: '[imagen]', isOut, msg_type: 'image', blobB64, imgSrc });
                    }
                    return msgs;
                }
                """

            raw_msgs_text = await page.evaluate(_extract_text_msgs_js())
            logger.info(f"[{session_id}] scrape '{contact_name}': {len(raw_msgs_text)} msgs texto en DOM (top)")
            # Dedup por (prePlain, body): al scrollear hacia abajo aparecen mensajes
            # recientes virtualizados. Incluir body evita descartar mensajes distintos
            # del mismo sender en el mismo minuto (mismo prePlain, diferente contenido).
            seen_text_keys: set[str] = {m["prePlain"] + "|" + m["body"] for m in raw_msgs_text}

            # 3b. Scroll lento hacia abajo para forzar render de mensajes de voz Y
            # capturar mensajes de texto recientes que estaban virtualizados al tope.
            # WA Web virtualiza: los mensajes del tope pueden desaparecer del DOM.
            total_height = await page.evaluate("""
            () => {
                for (const el of document.querySelectorAll('#main div')) {
                    if (el && el.scrollHeight > el.clientHeight && el.scrollHeight > 500)
                        return el.scrollHeight;
                }
                return 0;
            }
            """)
            raw_msgs_audio = []
            seen_audio_keys: set[str] = set()
            raw_msgs_docs = []
            seen_doc_keys: set[str] = set()
            raw_msgs_images = []
            seen_img_keys: set[str] = set()
            seen_img_hashes: set[str] = set()  # dedup por contenido binario
            step = 400
            for pos in range(0, total_height + step, step):
                await page.evaluate(f"""
                () => {{
                    for (const el of document.querySelectorAll('#main div')) {{
                        if (el && el.scrollHeight > el.clientHeight && el.scrollHeight > 500) {{
                            el.scrollTop = {pos};
                            return;
                        }}
                    }}
                }}
                """)
                await page.wait_for_timeout(350)
                # Capturar textos nuevos visibles en este paso (mensajes recientes)
                step_texts = await page.evaluate(_extract_text_msgs_js())
                for t in step_texts:
                    key = t["prePlain"] + "|" + t["body"]
                    if key not in seen_text_keys:
                        seen_text_keys.add(key)
                        raw_msgs_text.append(t)
                # Capturar audios visibles + descargar blob inline para PTT de grupos
                step_audios = await page.evaluate(f"() => {{ {_extract_audio_msgs_js()} }}")
                for a in step_audios:
                    key = a["prePlain"]
                    if key not in seen_audio_keys:
                        seen_audio_keys.add(key)
                        # Intentar descargar blob mientras está en DOM
                        if a.get("body") == "[audio]":
                            a["msg_type"] = "audio"  # marcar antes de que body cambie
                            import os as _os
                            audio_path = await self._download_visible_ptt_blob(page, session_id, key)
                            if audio_path:
                                try:
                                    from tools import transcription as _tr
                                    text = await _tr.transcribe(audio_path)
                                    a["body"] = text
                                    logger.info(f"[{session_id}] PTT histórico transcrito inline: {text[:60]}")
                                except Exception as exc:
                                    logger.warning(f"[{session_id}] Error transcribiendo PTT inline: {exc}")
                                finally:
                                    try:
                                        _os.unlink(audio_path)
                                    except Exception:
                                        pass
                        raw_msgs_audio.append(a)
                # Capturar documentos visibles en este paso
                step_docs = await page.evaluate(_extract_document_msgs_js())
                for d in step_docs:
                    key = d["prePlain"] + "|" + d["body"]
                    if key not in seen_doc_keys:
                        seen_doc_keys.add(key)
                        raw_msgs_docs.append(d)
                        # Descargar mientras el botón está en DOM
                        if doc_save_dir:
                            fn_m = re.search(r'`([^`]+)`', d["body"])
                            if fn_m:
                                fn = fn_m.group(1)
                                await self._download_document_from_page(page, fn, doc_save_dir / fn)
                # Capturar imágenes visibles en este paso y descargar blob inline
                step_imgs = await page.evaluate(_extract_image_msgs_js())
                for img in step_imgs:
                    key = img["prePlain"] + "|img"
                    if key not in seen_img_keys:
                        seen_img_keys.add(key)
                        blob_b64 = img.get("blobB64")
                        img_src = img.get("imgSrc")
                        # Retry: si el blob no cargó aún, esperar y reintentar con la URL guardada
                        if not blob_b64 and img_src:
                            await page.wait_for_timeout(1500)
                            try:
                                blob_b64 = await page.evaluate("""
                                async (src) => {
                                    try {
                                        const resp = await fetch(src);
                                        if (!resp.ok) return null;
                                        const buf = await resp.arrayBuffer();
                                        const bytes = new Uint8Array(buf);
                                        let bin = '';
                                        for (let b of bytes) bin += String.fromCharCode(b);
                                        return btoa(bin);
                                    } catch(e) { return null; }
                                }
                                """, img_src)
                            except Exception:
                                blob_b64 = None
                        # Guardar imagen en disco (con dedup por contenido)
                        if blob_b64:
                            import base64 as _b64_img
                            import time as _time_img
                            import hashlib as _hashlib_img
                            _img_bytes = _b64_img.b64decode(blob_b64)
                            _img_hash = _hashlib_img.sha256(_img_bytes).hexdigest()
                            if _img_hash in seen_img_hashes:
                                logger.debug(f"[{session_id}] Imagen duplicada (mismo contenido) omitida: {img['prePlain']}")
                                continue
                            seen_img_hashes.add(_img_hash)
                            # Filename estable basado en hash: el mismo archivo siempre
                            # tiene el mismo nombre → el dedup del summarizer lo detecta
                            # en syncs futuros sin limpiar el .md.
                            _img_fn = f"img_{_img_hash[:16]}.jpg"
                            _img_dir = doc_save_dir if doc_save_dir else None
                            if _img_dir:
                                _img_path = _img_dir / _img_fn
                                if not _img_path.exists():
                                    _img_path.write_bytes(_img_bytes)
                                img["body"] = f"[imagen guardada: {_img_fn}]"
                            else:
                                import os as _os_img
                                _img_path_str = f"/tmp/pulpo_img_{_img_fn}"
                                if not _os_img.path.exists(_img_path_str):
                                    with open(_img_path_str, "wb") as _f:
                                        _f.write(_img_bytes)
                                img["body"] = f"[imagen guardada: {_img_fn}]"
                            logger.info(f"[{session_id}] Imagen histórica descargada: {img['body']}")
                        else:
                            img["body"] = "[imagen — no disponible]"
                            logger.debug(f"[{session_id}] Imagen histórica: blob no accesible")
                        raw_msgs_images.append(img)

            logger.info(
                f"[{session_id}] scrape '{contact_name}': "
                f"scroll completo ({total_height}px), "
                f"{len(raw_msgs_text)} msgs texto total, "
                f"{len(raw_msgs_audio)} msgs audio/voz encontrados, "
                f"{len(raw_msgs_docs)} msgs documento encontrados, "
                f"{len(raw_msgs_images)} imgs encontradas"
            )

            # Scroll al fondo absoluto para asegurar que mensajes recientes
            # (que WA Web puede virtualizar durante el scroll-up) aparezcan en DOM.
            await page.evaluate("""
            () => {
                for (const el of document.querySelectorAll('#main div')) {
                    if (el && el.scrollHeight > el.clientHeight && el.scrollHeight > 500) {
                        el.scrollTop = el.scrollHeight;
                        return;
                    }
                }
            }
            """)
            await page.wait_for_timeout(1500)
            bottom_texts = await page.evaluate(_extract_text_msgs_js())
            bottom_audios = await page.evaluate(f"() => {{ {_extract_audio_msgs_js()} }}")
            bottom_docs = await page.evaluate(_extract_document_msgs_js())
            bottom_imgs = await page.evaluate(_extract_image_msgs_js())
            added_bottom = 0
            for t in bottom_texts:
                key = t["prePlain"] + "|" + t["body"]
                if key not in seen_text_keys:
                    seen_text_keys.add(key)
                    raw_msgs_text.append(t)
                    added_bottom += 1
            for a in bottom_audios:
                key = a["prePlain"]
                if key not in seen_audio_keys:
                    seen_audio_keys.add(key)
                    raw_msgs_audio.append(a)
                    added_bottom += 1
            for d in bottom_docs:
                key = d["prePlain"] + "|" + d["body"]
                if key not in seen_doc_keys:
                    seen_doc_keys.add(key)
                    raw_msgs_docs.append(d)
                    added_bottom += 1
            for img in bottom_imgs:
                key = img["prePlain"] + "|img"
                if key not in seen_img_keys:
                    seen_img_keys.add(key)
                    raw_msgs_images.append(img)
                    added_bottom += 1
            if added_bottom:
                logger.info(f"[{session_id}] scrape '{contact_name}': {added_bottom} msgs adicionales al scrollear al fondo")

            # Combinar: texto + audio + documentos + imágenes
            raw_msgs = raw_msgs_text + raw_msgs_audio + raw_msgs_docs + raw_msgs_images

            # 4. Parsear timestamps del atributo data-pre-plain-text
            # Formatos reales (locale es-AR):
            #   "[5:02 p. m., 17/3/2026] Sender: "   ← 12h, fecha después
            #   "[17:02, 17/3/2026] Sender: "         ← 24h, fecha después
            #   "[5:02 p. m.] Sender: "               ← solo hora (hoy)
            today = date.today()
            parsed = []
            for m in raw_msgs:
                pre = m.get("prePlain", "")
                # Normalizar \u00a0 (non-breaking space) en "p. m." / "a. m."
                pre_norm = pre.replace("\xa0", " ")
                ts = None
                sender = None

                # Extraer sender: lo que hay entre "] " y ": " al final
                snd_match = re.search(r"\]\s*(.+?):\s*$", pre_norm)
                if snd_match:
                    sender = snd_match.group(1).strip() or None

                # Intentar parsear fecha: "hh:mm [a/p]. m., DD/M/YYYY"
                date_m = re.search(
                    r"(\d{1,2}):(\d{2})(?:\s*([ap])\.?\s*m\.?)?,\s*(\d{1,2})/(\d{1,2})/(\d{4})",
                    pre_norm, re.IGNORECASE,
                )
                if date_m:
                    h, mi, ampm, d, mo, y = date_m.groups()
                    h, mi, d, mo, y = int(h), int(mi), int(d), int(mo), int(y)
                    if ampm:
                        if ampm.lower() == "p" and h != 12:
                            h += 12
                        elif ampm.lower() == "a" and h == 12:
                            h = 0
                    try:
                        ts = datetime(y, mo, d, h, mi).strftime("%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        pass
                else:
                    # Solo hora → asignar fecha de hoy
                    time_m = re.search(
                        r"(\d{1,2}):(\d{2})(?:\s*([ap])\.?\s*m\.?)?",
                        pre_norm, re.IGNORECASE,
                    )
                    if time_m:
                        h, mi, ampm = time_m.groups()
                        h, mi = int(h), int(mi)
                        if ampm:
                            if ampm.lower() == "p" and h != 12:
                                h += 12
                            elif ampm.lower() == "a" and h == 12:
                                h = 0
                        try:
                            ts = datetime(today.year, today.month, today.day, h, mi).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                        except ValueError:
                            pass

                if not ts:
                    continue

                # WA Web muestra la duración del audio ("0:01", "1:23") en
                # span.copyable-text cuando el player no está en el viewport.
                # Normalizar a [audio] para que el pasaje de transcripción lo procese.
                body = m["body"]
                if re.match(r'^\d{1,2}:\d{2}$', body):
                    body = "[audio]"

                parsed.append({
                    "timestamp": ts,
                    "sender": sender,
                    "body": body,
                    "is_outbound": m["isOut"],
                    "_raw_idx": m["idx"],
                    "_pre_plain": m.get("prePlain", ""),
                    "msg_type": m.get("msg_type", "text"),
                })

            logger.info(f"[{session_id}] scrape_full_history '{contact_name}': {len(parsed)} mensajes extraídos")

            # 5. Transcribir audios históricos (segundo pasaje: scroll al elemento, esperar blob)
            # Incluye [audio] (detectado en DOM) y [media] (vacío off-screen, puede ser audio)
            # Los mensajes de Parte B (source='audio', _raw_idx=-1) se guardan como [audio]
            # ya que el scroll lento ya los cargó — transcripción por índice no aplica.
            audio_entries = [(i, msg) for i, msg in enumerate(parsed) if msg["body"] in ("[audio]", "[media]")]
            # Marcar como audio antes de que el body sea reemplazado por la transcripción
            for _, _am in audio_entries:
                _am["msg_type"] = "audio"
            # Cargar claves IDB una sola vez como fallback cuando el blob DOM no esté visible.
            # Indexar por unix timestamp para búsqueda rápida (tolerancia ±120s).
            idb_audio_keys = await self._fetch_audio_idb_keys(page, session_id)
            idb_by_ts: list[dict] = sorted(idb_audio_keys, key=lambda k: k["t"])

            async def _transcribe_path(audio_path: str, parsed_idx: int, label: str) -> None:
                """Transcribe audio_path y actualiza parsed[parsed_idx]["body"]. Borra el tmp."""
                import os as _os2
                try:
                    text = await _transcription.transcribe(audio_path)
                    parsed[parsed_idx]["body"] = text
                    logger.info(f"[{session_id}] {label}: {text[:60]}")
                except Exception as exc:
                    parsed[parsed_idx]["body"] = "[audio — error al transcribir]"
                    logger.warning(f"[{session_id}] Error transcribiendo {label}: {exc}")
                finally:
                    try:
                        _os2.unlink(audio_path)
                    except Exception:
                        pass

            async def _try_idb_fallback(msg: dict, parsed_idx: int, label: str) -> bool:
                """Intenta CDN decrypt usando IDB. Retorna True si tuvo éxito."""
                from datetime import datetime as _dt
                ts = msg.get("timestamp")  # string como "2026-03-17 11:41:00"
                if not ts or not idb_by_ts:
                    return False
                try:
                    ts_unix = int(_dt.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp())
                except Exception:
                    return False
                # Búsqueda exacta (±120s)
                idb_match = next(
                    (k for k in idb_by_ts if abs(k["t"] - ts_unix) < 120),
                    None,
                )
                # Fallback: coincidencia por hora del día (±120s mod 86400)
                # Cubre el caso de fecha incorrecta en prePlain (heredada de mensaje anterior)
                if not idb_match:
                    ts_tod = ts_unix % 86400
                    idb_match = next(
                        (k for k in idb_by_ts if abs((k["t"] % 86400) - ts_tod) < 120),
                        None,
                    )
                    if idb_match:
                        logger.info(f"[{session_id}] IDB: coincidencia por hora del día para ts={ts} → idb t={idb_match['t']}")
                if not idb_match:
                    logger.debug(f"[{session_id}] IDB: sin coincidencia para ts={ts_unix}")
                    return False
                audio_path = await self._download_decrypt_audio_cdn(
                    idb_match["directPath"], idb_match["mediaKey"], session_id
                )
                if not audio_path:
                    return False
                await _transcribe_path(audio_path, parsed_idx, f"{label} (IDB CDN)")
                return True

            if audio_entries:
                import os
                from tools import transcription as _transcription
                logger.info(f"[{session_id}] Transcribiendo {len(audio_entries)} audios históricos de '{contact_name}'...")
                for parsed_idx, msg in audio_entries:
                    pre_plain = msg.get("_pre_plain", "")
                    raw_idx = msg["_raw_idx"]
                    original_body = msg["body"]
                    # Parte B (inline download ya intentado durante scroll): solo IDB fallback.
                    if raw_idx == -1:
                        if not await _try_idb_fallback(msg, parsed_idx, "Audio PTT Parte B"):
                            if original_body == "[audio]":
                                parsed[parsed_idx]["body"] = "[audio — sin blob]"
                        continue
                    # Parte A: buscar por data-pre-plain-text (robusto ante virtual DOM)
                    if not pre_plain:
                        continue
                    audio_path = await self._download_audio_blob_by_preplain(page, session_id, pre_plain)
                    if audio_path:
                        await _transcribe_path(audio_path, parsed_idx, "Audio histórico DOM")
                    else:
                        # DOM blob no disponible: fallback a IDB + CDN decrypt
                        if not await _try_idb_fallback(msg, parsed_idx, "Audio histórico"):
                            if original_body == "[audio]":
                                parsed[parsed_idx]["body"] = "[audio — sin blob]"

            # Asignar msg_type="text" a los que no sean audio
            for msg in parsed:
                msg.setdefault("msg_type", "text")

            # Limpiar campos internos antes de retornar
            for msg in parsed:
                msg.pop("_raw_idx", None)
                msg.pop("_pre_plain", None)

            # Filtrar por from_date si se especificó
            if from_date is not None:
                from datetime import datetime as _dt
                cutoff = _dt.combine(from_date, _dt.min.time())
                def _msg_date(m):
                    ts = m.get("timestamp")
                    if not ts:
                        return None
                    try:
                        return _dt.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        return None
                parsed = [m for m in parsed if (_msg_date(m) is None or _msg_date(m) >= cutoff)]
                logger.info(f"[{session_id}] scrape '{contact_name}': {len(parsed)} mensajes tras filtro from_date={from_date}")

            return parsed

        except Exception as e:
            logger.warning(f"[{session_id}] scrape_full_history error para '{contact_name}': {e}")
            return []

    # ------------------------------------------------------------------
    # scrape_full_history_v2 — arquitectura mensaje-primero
    # ------------------------------------------------------------------

    async def scrape_full_history_v2(
        self,
        session_id: str,
        contact_name: str,
        doc_save_dir: "Path | None" = None,
        stop_before_ts: "datetime | None" = None,
        max_scroll_rounds: int = 120,
    ) -> list[dict]:
        """
        Reemplaza scrape_full_history con arquitectura correcta:
        - La entidad es el MENSAJE, no el tipo de contenido.
        - Un solo loop: por cada mensaje visible → extraer TODO (texto / audio / doc / imagen).
        - Empieza por el más reciente (fondo) y sube.
        - Para cuando todos los mensajes visibles son anteriores a stop_before_ts (delta).
        - Sin IDB, sin timestamp matching, sin fallbacks inventados.
        - Audio: click play → esperar blob (15s) → transcribir. Si no llega → sin blob.
        """
        import re as _re
        import base64 as _b64
        import time as _time_mod
        import os as _os
        import hashlib as _hashlib
        from datetime import datetime as _dt

        page = self.get_page(session_id)
        if not page:
            return []

        # ── JS: función auxiliar de fecha (reutilizada en el scan) ──────────
        _DATE_HELPERS_JS = r"""
        const _today = new Date();
        const _monthES = {
            'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,
            'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12
        };
        const _dayES = {
            'domingo':0,'lunes':1,'martes':2,'miercoles':3,'miércoles':3,
            'jueves':4,'viernes':5,'sabado':6,'sábado':6
        };
        function _dateFromStr(dateStr) {
            // "DD/MM/YYYY" → Date
            const [d,m,y] = dateStr.split('/').map(Number);
            return new Date(y, m-1, d);
        }
        function _nearestDateBefore(container) {
            // Fecha del data-pre-plain-text más cercano + separadores de día
            let msgDate = '';
            let lastPPEl = null;
            for (const el of document.querySelectorAll('[data-pre-plain-text]')) {
                if (!(container.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) break;
                const m = el.getAttribute('data-pre-plain-text').match(/(\d{1,2}\/\d{1,2}\/\d{4})/);
                if (m) { lastPPEl = el; msgDate = m[1]; }
            }
            for (const el of document.querySelectorAll('span')) {
                if (lastPPEl && !(lastPPEl.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
                if (!(container.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) break;
                const ownTxt = [...el.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent.trim()).join('').trim();
                if (!ownTxt || ownTxt.length > 60) continue;
                const low = ownTxt.toLowerCase()
                    .replace(/\u00e9/g,'e').replace(/\u00e1/g,'a')
                    .replace(/\u00f3/g,'o').replace(/\u00fa/g,'u');
                let sepDate = null;
                const fd = ownTxt.match(/(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})/i);
                if (fd) {
                    const d=parseInt(fd[1]),mo=_monthES[fd[2].toLowerCase()]||0,y=parseInt(fd[3]);
                    if (mo) sepDate = d+'/'+mo+'/'+y;
                } else if (low==='hoy') {
                    sepDate = _today.getDate()+'/'+(_today.getMonth()+1)+'/'+_today.getFullYear();
                } else if (low==='ayer') {
                    const d2=new Date(_today); d2.setDate(d2.getDate()-1);
                    sepDate = d2.getDate()+'/'+( d2.getMonth()+1)+'/'+d2.getFullYear();
                } else if (_dayES[low]!==undefined) {
                    const target=_dayES[low];
                    let ago=(_today.getDay()-target+7)%7; if(ago===0)ago=7;
                    const d3=new Date(_today); d3.setDate(d3.getDate()-ago);
                    sepDate = d3.getDate()+'/'+( d3.getMonth()+1)+'/'+d3.getFullYear();
                }
                if (sepDate) { msgDate = sepDate; break; }
            }
            return msgDate;
        }
        function _getTime(container) {
            const w = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
            let n, t='';
            while (n=w.nextNode()) {
                const s=n.textContent.trim();
                if (/^\d{1,2}:\d{2}(\s*(a|p)[\.\s]*m\.?)?$/i.test(s)) t=s;
            }
            return t;
        }
        function _getSender(container) {
            const els = [
                container.querySelector('[data-testid="author"]'),
                container.querySelector('span[aria-label$=":"]'),
                container.querySelector('span[style*="color:#"],span[style*="color: #"]'),
                container.querySelector('._ak4h span[dir="auto"]'),
            ];
            for (const el of els) {
                if (!el) continue;
                const v = el.hasAttribute('aria-label')
                    ? (el.getAttribute('aria-label')||'').replace(/:$/,'').trim()
                    : el.innerText.trim();
                if (v) return v;
            }
            return '';
        }
        """

        # ── JS: escanear mensajes visibles NO procesados ─────────────────────
        _SCAN_JS = f"""
        () => {{
            {_DATE_HELPERS_JS}
            const results = [];
            const allContainers = document.querySelectorAll(
                '.message-in:not([data-pulpo-done]), .message-out:not([data-pulpo-done])'
            );
            for (const c of allContainers) {{
                const rect = c.getBoundingClientRect();
                if (rect.bottom < -300 || rect.top > window.innerHeight + 300) continue;

                const isOut = c.classList.contains('message-out');

                // ── Detectar tipo ──────────────────────────────────────────
                const ppEl = c.querySelector('[data-pre-plain-text]');
                const audioInd = c.querySelector(
                    '[data-icon="ptt-status"],[data-icon="ptt-play"],[data-icon="audio-play"],' +
                    'button[aria-label*="voz"],button[aria-label*="voice"],' +
                    'button[aria-label*="Voice"],button[aria-label*="Reproducir"]'
                );
                const imgEl = !ppEl ? c.querySelector('img[src^="blob:"]') : null;

                // ── Timestamp ─────────────────────────────────────────────
                let time='', date='', sender='';
                if (ppEl) {{
                    const pp = ppEl.getAttribute('data-pre-plain-text')||'';
                    const m = pp.match(/\\[(\\d{{1,2}}:\\d{{2}}(?:\\s*[ap]\\.?m\\.?)?),?\\s*(\\d{{1,2}}\\/\\d{{1,2}}\\/\\d{{4}})\\]\\s*(.*?):\\s*$/i);
                    if (m) {{ time=m[1].trim(); date=m[2]; sender=m[3].trim(); }}
                    else {{
                        const m2 = pp.match(/\\[(\\d{{1,2}}:\\d{{2}}(?:\\s*[ap]\\.?m\\.?)?),?\\s*(\\d{{1,2}}\\/\\d{{1,2}}\\/\\d{{4}})\\]/i);
                        if (m2) {{ time=m2[1].trim(); date=m2[2]; }}
                    }}
                }} else {{
                    time = _getTime(c);
                    date = _nearestDateBefore(c);
                    sender = _getSender(c);
                }}
                if (!time) {{ c.setAttribute('data-pulpo-done','1'); continue; }}

                // ── Audio sin data-pre-plain-text ─────────────────────────
                if (audioInd && !ppEl) {{
                    const btn = c.querySelector(
                        'button[aria-label*="voz"],button[aria-label*="voice"],' +
                        'button[aria-label*="Voice"],button[aria-label*="Reproducir"],' +
                        'button[aria-label*="Escuchar"]'
                    ) || audioInd.closest('button') || audioInd.parentElement?.querySelector('button');
                    const aid = 'pa-' + Date.now() + '-' + Math.random().toString(36).slice(2,8);
                    if (btn) btn.setAttribute('data-pulpo-audio-id', aid);
                    c.setAttribute('data-pulpo-done','1');
                    results.push({{ type:'audio', time, date, sender, isOut, audioId: btn ? aid : null }});
                    continue;
                }}

                // ── Imagen sin caption ────────────────────────────────────
                if (imgEl) {{
                    c.setAttribute('data-pulpo-done','1');
                    results.push({{ type:'image', time, date, sender, isOut, imgSrc: imgEl.src }});
                    continue;
                }}

                // ── Texto (incluye audio CON caption, docs con caption) ───
                if (ppEl) {{
                    // Sub-tipo audio con data-pre-plain-text (raro pero posible)
                    if (audioInd) {{
                        const btn = c.querySelector(
                            'button[aria-label*="voz"],button[aria-label*="voice"],' +
                            'button[aria-label*="Voice"],button[aria-label*="Reproducir"]'
                        ) || audioInd.closest('button');
                        const aid = 'pa-' + Date.now() + '-' + Math.random().toString(36).slice(2,8);
                        if (btn) btn.setAttribute('data-pulpo-audio-id', aid);
                        c.setAttribute('data-pulpo-done','1');
                        results.push({{ type:'audio', time, date, sender, isOut, audioId: btn ? aid : null }});
                        continue;
                    }}
                    // Documento
                    const docNameEl = c.querySelector('[data-testid="document-title"]');
                    if (docNameEl) {{
                        const fname = docNameEl.innerText.trim();
                        const sizeEl = c.querySelector('[data-testid="document-size"]');
                        const fsize = sizeEl ? sizeEl.innerText.trim() : '';
                        c.setAttribute('data-pulpo-done','1');
                        results.push({{ type:'document', time, date, sender, isOut, filename: fname, size: fsize }});
                        continue;
                    }}
                    // Texto plano
                    const children = [...ppEl.children];
                    let body='', quoted='';
                    if (children.length >= 2) {{
                        const realEl = children[children.length-1].querySelector('span.copyable-text,[data-testid="selectable-text"]');
                        body = realEl ? realEl.innerText.trim() : '';
                        const qEl = children[0].querySelector('span.copyable-text,[data-testid="selectable-text"]');
                        quoted = qEl ? qEl.innerText.trim() : '';
                    }} else {{
                        const textEl = ppEl.querySelector('span.copyable-text,[data-testid="msg-text"]');
                        body = textEl ? textEl.innerText.trim() : ppEl.innerText.trim();
                    }}
                    // Duración de audio raw ("1:55") → es audio sin botón aún cargado
                    if (!body || /^\\d{{1,2}}:\\d{{2}}$/.test(body.trim())) {{
                        c.setAttribute('data-pulpo-done','1');
                        results.push({{ type:'audio', time, date, sender, isOut, audioId: null }});
                        continue;
                    }}
                    c.setAttribute('data-pulpo-done','1');
                    results.push({{ type:'text', time, date, sender, isOut, body, quoted }});
                }}
            }}
            return results;
        }}
        """

        # ── JS: click audio por data-pulpo-audio-id ──────────────────────────
        _CLICK_AUDIO_JS = """
        (audioId) => {
            const btn = document.querySelector('[data-pulpo-audio-id="' + audioId + '"]');
            if (!btn) return false;
            if (window.__capturedAudioBlobsB64) window.__capturedAudioBlobsB64 = [];
            btn.scrollIntoView({ block: 'center', behavior: 'instant' });
            btn.click();
            return true;
        }
        """

        # ── JS: scrollear un paso hacia arriba ───────────────────────────────
        _SCROLL_UP_JS = """
        (step) => {
            for (const el of document.querySelectorAll('#main div')) {
                if (el.scrollHeight > el.clientHeight && el.scrollHeight > 500 && el.scrollTop > 0) {
                    const prev = el.scrollTop;
                    el.scrollTop = Math.max(0, el.scrollTop - step);
                    return prev !== el.scrollTop;
                }
            }
            return false;
        }
        """

        # ── JS: scroll al fondo ───────────────────────────────────────────────
        _SCROLL_BOTTOM_JS = """
        () => {
            for (const el of document.querySelectorAll('#main div')) {
                if (el.scrollHeight > el.clientHeight && el.scrollHeight > 500) {
                    el.scrollTop = el.scrollHeight;
                    return;
                }
            }
        }
        """

        # ── Helpers Python ────────────────────────────────────────────────────
        def _parse_ts(time: str, date: str) -> str | None:
            """'HH:MM, DD/MM/YYYY' → 'YYYY-MM-DD HH:MM:SS'"""
            if not time or not date:
                return None
            try:
                # Normalizar hora 12h → 24h
                t = time.strip()
                is_pm = bool(_re.search(r'p\.?m\.?', t, _re.I))
                is_am = bool(_re.search(r'a\.?m\.?', t, _re.I))
                t = _re.sub(r'\s*(a|p)\.?m\.?.*', '', t, flags=_re.I).strip()
                h, m = map(int, t.split(':'))
                if is_pm and h != 12:
                    h += 12
                elif is_am and h == 12:
                    h = 0
                d, mo, y = map(int, date.split('/'))
                return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{m:02d}:00"
            except Exception:
                return None

        async def _wait_blob(timeout_ms: int = 15000) -> str | None:
            """Espera hasta timeout_ms que el interceptor capture un blob."""
            for _ in range(timeout_ms // 200):
                await page.wait_for_timeout(200)
                b64 = await page.evaluate(
                    "() => window.__capturedAudioBlobsB64?.shift() || null"
                )
                if b64:
                    return b64
                # Fallback: fetch directo del elemento <audio> en DOM
                b64 = await page.evaluate("""
                async () => {
                    const a = document.querySelector('audio[src^="blob:"]');
                    if (!a) return null;
                    try {
                        const r = await fetch(a.src);
                        if (!r.ok) return null;
                        const buf = await r.arrayBuffer();
                        const bytes = new Uint8Array(buf);
                        let bin=''; for (const b of bytes) bin+=String.fromCharCode(b);
                        return btoa(bin);
                    } catch(e) { return null; }
                }
                """)
                if b64:
                    return b64
            return None

        async def _transcribe_b64(b64: str) -> str | None:
            path = f"/tmp/pulpo_audio_{int(_time_mod.time()*1000)}.ogg"
            try:
                with open(path, "wb") as f:
                    f.write(_b64.b64decode(b64))
                from tools import transcription as _tr
                return await _tr.transcribe(path)
            except Exception as exc:
                logger.warning(f"[{session_id}] v2 transcribe error: {exc}")
                return None
            finally:
                try:
                    _os.unlink(path)
                except Exception:
                    pass

        async def _save_image_b64(b64: str, save_dir: "Path") -> str | None:
            try:
                data = _b64.b64decode(b64)
                digest = _hashlib.sha256(data).hexdigest()[:16]
                fn = f"img_{digest}.jpg"
                p = save_dir / fn
                if not p.exists():
                    p.write_bytes(data)
                return fn
            except Exception:
                return None

        # ──────────────────────────────────────────────────────────────────────
        try:
            # 1. Abrir chat
            def _normalize(s: str) -> str:
                import unicodedata
                return unicodedata.normalize("NFKC", s).strip()

            row_handle = await page.evaluate_handle(
                """(target) => {
                    const norm = s => s.replace(/[\\u00a0\\u202a\\u202c\\u200e\\u200f]/g, ' ').trim();
                    const grid = document.querySelector('[role="grid"]');
                    if (!grid) return null;
                    for (const s of grid.querySelectorAll('span[title]')) {
                        if (norm(s.getAttribute('title')) === norm(target))
                            return s.closest('[role="row"]') || s.closest('[data-id]') || s;
                    }
                    return null;
                }""",
                _normalize(contact_name),
            )
            if not row_handle or await row_handle.evaluate("el => el === null"):
                logger.warning(f"[{session_id}] v2: no encontré '{contact_name}' en el sidebar")
                return []
            await row_handle.scroll_into_view_if_needed()
            await row_handle.click()
            await page.wait_for_timeout(2000)

            # 2. Instalar interceptor de blobs
            await self._install_blob_interceptor(page)

            # 3. Ir al fondo (mensajes más recientes)
            await page.evaluate(_SCROLL_BOTTOM_JS)
            await page.wait_for_timeout(1500)

            results: list[dict] = []
            seen_keys: set[str] = set()
            stale_rounds = 0

            # 4. Loop principal: escanear → procesar → subir
            for _round in range(max_scroll_rounds):
                batch = await page.evaluate(_SCAN_JS)

                new_in_batch = 0
                for msg in batch:
                    ts_str = _parse_ts(msg.get("time", ""), msg.get("date", ""))
                    key = f"{ts_str}|{msg.get('sender','')}|{msg.get('type','')}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    new_in_batch += 1

                    # ── Condición de parada (delta sync) ──────────────────
                    if stop_before_ts and ts_str:
                        try:
                            msg_dt = _dt.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                            if msg_dt <= stop_before_ts:
                                logger.info(f"[{session_id}] v2: delta alcanzado en {ts_str}")
                                return results
                        except Exception:
                            pass

                    entry: dict = {
                        "timestamp": ts_str,
                        "sender": msg.get("sender") or None,
                        "is_outbound": msg.get("isOut", False),
                        "msg_type": msg["type"],
                        "body": "",
                    }

                    # ── Procesar por tipo ──────────────────────────────────
                    if msg["type"] == "audio":
                        audio_id = msg.get("audioId")
                        if audio_id:
                            clicked = await page.evaluate(_CLICK_AUDIO_JS, audio_id)
                            if clicked:
                                b64 = await _wait_blob(timeout_ms=15000)
                                if b64:
                                    # Pausar audio
                                    await page.evaluate("() => { try { document.querySelector('audio')?.pause(); } catch(e){} }")
                                    text = await _transcribe_b64(b64)
                                    if text:
                                        entry["body"] = text
                                        logger.info(f"[{session_id}] v2 audio OK: {text[:60]}")
                                    else:
                                        entry["body"] = "[audio — error al transcribir]"
                                else:
                                    entry["body"] = "[audio — sin blob]"
                                    logger.info(f"[{session_id}] v2 audio sin blob (CDN expirado o cargando): {ts_str}")
                            else:
                                entry["body"] = "[audio — sin blob]"
                        else:
                            entry["body"] = "[audio — sin blob]"

                    elif msg["type"] == "image":
                        img_src = msg.get("imgSrc", "")
                        if img_src and doc_save_dir:
                            b64 = await page.evaluate("""
                            async (src) => {
                                try {
                                    const r = await fetch(src);
                                    if (!r.ok) return null;
                                    const buf = await r.arrayBuffer();
                                    const bytes = new Uint8Array(buf);
                                    let bin=''; for (const b of bytes) bin+=String.fromCharCode(b);
                                    return btoa(bin);
                                } catch(e) { return null; }
                            }
                            """, img_src)
                            if b64:
                                fn = await _save_image_b64(b64, doc_save_dir)
                                entry["body"] = f"[imagen guardada: {fn}]" if fn else "[imagen]"
                            else:
                                entry["body"] = "[imagen]"
                        else:
                            entry["body"] = "[imagen]"

                    elif msg["type"] == "document":
                        fname = msg.get("filename", "")
                        fsize = msg.get("size", "")
                        entry["body"] = f"`{fname}` ({fsize})" if fsize else f"`{fname}`"
                        if fname and doc_save_dir:
                            await self._download_document_from_page(page, fname, doc_save_dir / fname)

                    else:  # text
                        body = msg.get("body", "")
                        quoted = msg.get("quoted", "")
                        entry["body"] = body
                        if quoted:
                            entry["quoted"] = quoted

                    results.append(entry)

                # ── Stale detection + scroll up ────────────────────────────
                if new_in_batch == 0:
                    stale_rounds += 1
                    if stale_rounds >= 4:
                        logger.info(f"[{session_id}] v2: sin mensajes nuevos, fin del historial")
                        break
                else:
                    stale_rounds = 0

                scrolled = await page.evaluate(_SCROLL_UP_JS, 600)
                await page.wait_for_timeout(700)
                if not scrolled:
                    stale_rounds += 1

            logger.info(f"[{session_id}] v2 scrape_full_history '{contact_name}': {len(results)} mensajes")
            return results

        except Exception as e:
            logger.warning(f"[{session_id}] scrape_full_history_v2 error: {e}", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    async def is_connected(self, session_id: str) -> bool:
        """True si la página existe, responde, y no está mostrando el QR."""
        if not await self.is_page_alive(session_id):
            return False
        page = self.get_page(session_id)
        try:
            qr = await page.query_selector("canvas[aria-label], div[data-ref]")
            return qr is None
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Envío de mensajes — usa página temporal para no interrumpir el observer
    # ------------------------------------------------------------------

    async def purge_drafts(self, session_id: str) -> int:
        """
        Recorre todos los chats con borrador en WA Web y limpia el compose box.
        Usa la Store interna de WA para encontrar los chats afectados, luego
        hace click + Ctrl+A + Backspace en cada uno.
        Devuelve la cantidad de borradores eliminados.
        """
        page = self.get_page(session_id)
        if not page:
            logger.warning(f"[{session_id}] purge_drafts: no hay página activa")
            return 0

        compose_sel = (
            "footer [contenteditable='true'], "
            "[data-testid='conversation-compose-box-input'] [contenteditable='true'], "
            "[contenteditable='true'][spellcheck='true']"
        )

        try:
            # Obtener chats con borrador via Store interna de WA Web
            draft_ids: list = await page.evaluate("""
                () => {
                    // Intento 1: Store interna de WA Web
                    try {
                        const store = window.Store && window.Store.Chat;
                        if (store && store.getModelsArray) {
                            const ids = store.getModelsArray()
                                .filter(c => c.hasDraftMessage || (c.draft && c.draft.trim() !== ''))
                                .map(c => c.id && (c.id.user || c.id._serialized || ''))
                                .filter(Boolean);
                            if (ids.length > 0) return ids;
                        }
                    } catch(e) {}

                    // Intento 2: buscar filas del sidebar que contengan el texto "Borrador"
                    const ids = [];
                    const rows = document.querySelectorAll('[role="row"], [data-testid="cell-frame-container"], [tabindex="-1"]');
                    rows.forEach(row => {
                        const text = row.innerText || '';
                        if (text.includes('Borrador') || text.includes('Draft')) {
                            // Buscar el título del contacto en la fila
                            const titleEl = row.querySelector('span[title], [title]');
                            if (titleEl) {
                                const t = titleEl.getAttribute('title');
                                if (t && t.trim()) ids.push(t.trim());
                            }
                        }
                    });
                    return [...new Set(ids)];
                }
            """)

            if not draft_ids:
                logger.info(f"[{session_id}] purge_drafts: sin borradores")
                return 0

            cleared = 0
            for contact_id in draft_ids:
                try:
                    contact_span = page.locator(
                        f"[role='grid'] span[title='{contact_id}']"
                    ).first
                    if not await contact_span.is_visible(timeout=2000):
                        continue
                    await contact_span.click()

                    compose = page.locator(compose_sel).first
                    await compose.wait_for(state="visible", timeout=4000)
                    await compose.click()
                    await page.keyboard.press("Control+a")
                    await page.keyboard.press("Backspace")
                    await page.wait_for_timeout(300)
                    cleared += 1
                    logger.info(f"[{session_id}] purge_drafts: borrador eliminado de '{contact_id}'")
                except Exception as e:
                    logger.warning(f"[{session_id}] purge_drafts: no se pudo limpiar '{contact_id}': {e}")

            logger.info(f"[{session_id}] purge_drafts: {cleared}/{len(draft_ids)} borradores eliminados")
            return cleared

        except Exception as e:
            logger.error(f"[{session_id}] purge_drafts error: {e}")
            return 0

    async def send_message(self, session_id: str, phone: str, text: str) -> bool:
        """
        Envía un mensaje clickeando el chat en el sidebar de la página principal.
        NO abre nueva pestaña — evita el popup "Usar aquí" de WA Web.
        phone: número (preferido, extraído de data-id) o nombre como fallback.
        """
        page = self.get_page(session_id)
        if not page:
            logger.warning(f"[{session_id}] send_message: no hay página activa")
            return False

        try:
            # Usar Playwright click real (no JS .click()) para activar los handlers React
            # Buscar el span con el nombre/número del contacto en el sidebar
            contact_span = page.locator(
                f"[role='grid'] span[title='{phone}']"
            ).first
            await contact_span.wait_for(state="visible", timeout=5000)
            await contact_span.click()

            # Esperar que el compose box aparezca
            compose = page.locator(
                "footer [contenteditable='true'], "
                "[data-testid='conversation-compose-box-input'] [contenteditable='true'], "
                "[contenteditable='true'][spellcheck='true']"
            ).first
            await compose.wait_for(state="visible", timeout=SEND_TIMEOUT_MS)
            await compose.click()
            await page.keyboard.type(text)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(800)

            logger.info(f"[{session_id}] Mensaje enviado a {phone}")
            return True

        except Exception as e:
            logger.error(f"[{session_id}] Error enviando mensaje a {phone}: {e}")
            return False


# ------------------------------------------------------------------
# Helpers internos
# ------------------------------------------------------------------

async def _passes_any_flow_filter(connection_id: str, name: str, phone: str) -> bool:
    """
    Verifica si un contacto (name/phone) califica en al menos un flow activo
    de la conexión. Si no hay flows → True (sin restricción). Si hay flows
    pero ninguno acepta este contacto → False (descartar sin loguear).
    """
    import json as _json
    from db import AsyncSessionLocal, text as _text

    async with AsyncSessionLocal() as sess:
        rows = (await sess.execute(_text("""
            SELECT json_extract(definition, '$.nodes[0].config.contact_filter') AS cf
            FROM flows
            WHERE active = 1
              AND json_extract(definition, '$.nodes[0].config.connection_id') = :conn
        """), {"conn": connection_id})).fetchall()

    if not rows:
        return True  # sin flows configurados → no filtrar

    for (cf_raw,) in rows:
        if not cf_raw:
            return True  # flow sin filtro → acepta todo
        cf = _json.loads(cf_raw) if isinstance(cf_raw, str) else cf_raw
        if not cf:
            return True

        excluded = cf.get("excluded", [])
        included = cf.get("included", [])
        inc_all  = cf.get("include_all_known", False)
        inc_unk  = cf.get("include_unknown", False)

        if name in excluded or phone in excluded:
            continue  # este flow lo excluye, probar siguiente

        if name in included or phone in included:
            return True
        if inc_all or inc_unk:
            return True  # filtro abierto (todos los conocidos / desconocidos)

    return False  # ningún flow lo acepta


def _update(session_id: str, *, connection_id: str = "", status: str, qr: str | None = None) -> None:
    if session_id not in clients:
        clients[session_id] = {"connection_id": connection_id, "type": "whatsapp", "client": None, "qr": None}
    if connection_id:
        clients[session_id]["connection_id"] = connection_id
    clients[session_id]["status"] = status
    if qr is not None or status in ("connecting", "failed", "ready"):
        clients[session_id]["qr"] = qr
