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

    async def connect(self, session_id: str, bot_id: str) -> str:
        """
        Intenta conectar la sesión usando el perfil Chrome persistente:
          1. Si el perfil en disco tiene sesión válida → la restaura.
          2. Si no → navega a WA Web y espera QR.

        Espera a que aparezca la UI principal (autenticado) O el QR,
        lo que llegue primero. Evita falsos positivos durante la carga.

        Retorna: "restored" | "qr_needed" | "failed"
        """
        _update(session_id, bot_id=bot_id, status="connecting")

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
        from sim import resolve_tools
        from config import get_empresas_for_bot

        recent_msgs: set[tuple[str, str]] = set()  # dedup entre JS y Python poll

        async def _on_message(phone: str, name: str, body: str) -> None:
            # Dedup: mismo (name, body) ya procesado recientemente
            pair = (name, body)
            if pair in recent_msgs:
                return
            recent_msgs.add(pair)
            asyncio.get_event_loop().call_later(60, lambda: recent_msgs.discard(pair))

            logger.info(f"[{session_id}] Mensaje de {name} ({phone}): {body[:60]}")

            # Dispatch multi-empresa: loguar bajo todos los bots que tienen esta conexión
            empresa_ids = get_empresas_for_bot(bot_phone)
            if not empresa_ids:
                empresa_ids = [bot_id]

            msg_ids = {}
            for eid in empresa_ids:
                mid = await log_message(eid, bot_phone, phone or name, name, body)
                msg_ids[eid] = mid

            # Motor de resolución: herramientas en DB
            # WA usa el nombre como identificador (phone suele llegar vacío del scraper)
            sender = phone or name
            summarizers, tool = await resolve_tools(session_id, sender, "whatsapp")

            # Si el contacto es un grupo, parsear "Integrante: mensaje"
            # El sidebar de WA Web muestra el body como "NombreRemitente: texto"
            sender_in_group: str | None = None
            if summarizers or tool:
                from db import find_contact_by_channel
                contact = await find_contact_by_channel("whatsapp", sender)
                if contact:
                    ch = next((c for c in contact.get("channels", [])
                               if c["type"] == "whatsapp" and c.get("is_group")), None)
                    if ch and ": " in body:
                        parts = body.split(": ", 1)
                        sender_in_group = parts[0].strip()
                        body = parts[1].strip()
                        logger.debug(f"[{session_id}] Grupo '{name}' — remitente: {sender_in_group}")

            # Acumular en summarizers activos
            if summarizers:
                from tools import summarizer as summarizer_mod
                from datetime import datetime

                # Detectar si es un audio (el sidebar WA Web muestra 🎵, 🎤 o "Audio")
                _AUDIO_MARKERS = ("🎵", "🎤", "Audio", "audio", "Voice message")
                # WA Web muestra la duración del audio ("0:01", "1:23") cuando el
                # player no está cargado — mismo patrón que en scrape_full_history
                import re as _re
                is_audio = any(m in body for m in _AUDIO_MARKERS) or bool(_re.match(r'^\d{1,2}:\d{2}$', body))

                if is_audio:
                    audio_path = await self._download_audio_blob(page, name, session_id)
                    if audio_path:
                        from tools import transcription
                        import os
                        try:
                            audio_content = await transcription.transcribe(audio_path)
                            logger.info(f"[{session_id}] Audio transcrito de {name}: {audio_content[:60]}")
                        except Exception as _te:
                            logger.warning(f"[{session_id}] Transcripción fallida: {_te}")
                            audio_content = "[audio — error al transcribir]"
                        finally:
                            try:
                                os.unlink(audio_path)
                            except Exception:
                                pass
                    else:
                        audio_content = "[audio — pendiente transcripción]"
                        logger.info(f"[{session_id}] Audio de {name} sin blob disponible")
                else:
                    audio_content = None

                # Para grupos: el content incluye el remitente dentro del grupo
                def _group_content(raw: str) -> str:
                    if sender_in_group:
                        return f"{sender_in_group}: {raw}"
                    return raw

                for s_tool in summarizers:
                    if is_audio:
                        summarizer_mod.accumulate(
                            empresa_id=s_tool["empresa_id"],
                            contact_phone=sender,
                            contact_name=name,
                            msg_type="audio",
                            content=_group_content(audio_content),
                            timestamp=datetime.now(),
                        )
                    else:
                        summarizer_mod.accumulate(
                            empresa_id=s_tool["empresa_id"],
                            contact_phone=sender,
                            contact_name=name,
                            msg_type="text",
                            content=_group_content(body),
                            timestamp=datetime.now(),
                        )

            if not tool:
                logger.debug(f"[{session_id}] Sin herramienta activa para '{name}'")
                return

            if tool["tipo"] == "fixed_message":
                reply = tool["config"].get("message", "")
            else:
                reply = ""

            if not reply or body.strip() == reply.strip():
                return

            # Enviamos en página temporal para no interrumpir el observer
            target = phone if phone else name
            ok = await self.send_message(session_id, target, reply)
            if ok:
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
            let sidebarReady = false; // primera pasada solo inicializa, no dispara

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

                    // Primera pasada: solo registrar estado, no disparar
                    if (!sidebarReady) { lastPreview[name] = body; continue; }

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

                    try { await __waOnMessage('', name, body); }
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

                const bodyEl = lastMsg.querySelector('span.copyable-text, [data-testid="msg-text"]');
                const body = (bodyEl?.textContent || '').trim();
                if (!body) return;

                // Key por conteo + texto: detecta mensajes nuevos aunque el texto sea igual
                const key = 'open|' + name + '|' + allMsgs.length + '|' + body;
                if (key === lastOpenChatKey) return;
                lastOpenChatKey = key;

                if (seen.has(key)) return;
                seen.add(key);
                setTimeout(() => seen.delete(key), 60000);

                try { await __waOnMessage('', name, body); }
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

    async def _poll_open_chat(self, session_id: str, page, on_message) -> None:
        """
        Corre en background: cada 3s evalúa JS en la página WA para obtener
        el último mensaje del chat abierto y llama al handler Python.
        Cubre el caso de 'Message yourself' y chats que no tienen badge de no leídos.
        """
        seen_pairs: set[tuple[str, str]] = set()  # (name, body) ya procesados
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

                        // Intentar extraer número de teléfono del atributo data-id
                        const withId = row.closest('[data-id]') || row.querySelector('[data-id]');
                        const rawId = withId ? withId.getAttribute('data-id') : '';
                        const phoneMatch = rawId ? rawId.match(/(\\d{8,15})/) : null;
                        const phone = phoneMatch ? phoneMatch[1] : '';

                        chats.push({ name, body, phone });
                    }
                    if (!chats.length) return null;
                    return { chats, count: rows.length };
                }
                """)

                if not result:
                    continue

                # Comparar cada chat con su último preview conocido
                for chat in result["chats"]:
                    name, body, phone = chat["name"], chat["body"], chat.get("phone", "")
                    pair = (name, body)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    logger.debug(f"[{session_id}] open-chat detectó: {name} ({phone}) → {body[:40]}")
                    await on_message(phone, name, body)

            except Exception as e:
                if "closed" in str(e).lower() or "target" in str(e).lower():
                    break
                logger.info(f"[{session_id}] _poll_open_chat error: {e}")

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

    # ------------------------------------------------------------------
    # Scraping histórico
    # ------------------------------------------------------------------

    async def scrape_full_history(
        self, session_id: str, contact_name: str, scroll_rounds: int = 50
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
                        const textEl = el.querySelector('span.copyable-text, [data-testid="msg-text"]');
                        const body = textEl ? textEl.innerText.trim() : '';
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
                () => {
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
                        let anc = msgContainer.parentElement;
                        for (let j = 0; j < 12 && anc; j++) {
                            const ppEl = anc.querySelector('[data-pre-plain-text]');
                            if (ppEl) {
                                const m = ppEl.getAttribute('data-pre-plain-text').match(/(\d{1,2}\/\d{1,2}\/\d{4})/);
                                if (m) { msgDate = m[1]; break; }
                            }
                            anc = anc.parentElement;
                        }

                        let timeText = '';
                        if (msgTime && msgDate)       timeText = msgTime + ', ' + msgDate;
                        else if (msgTime)              timeText = msgTime;
                        if (!timeText) continue;

                        // Sender: span[aria-label="Name:"] (grupos) o data-testid="author"
                        const senderAriaEl = msgContainer.querySelector('span[aria-label$=":"]');
                        const senderTestEl = msgContainer.querySelector('[data-testid="author"]');
                        const senderEl = senderAriaEl || senderTestEl
                                      || msgContainer.querySelector('span[style*="color"]');
                        let sender = '';
                        if (senderAriaEl) {
                            sender = (senderAriaEl.getAttribute('aria-label') || '').replace(/:$/, '').trim();
                        } else if (senderTestEl) {
                            sender = senderTestEl.innerText.trim();
                        } else if (senderEl) {
                            sender = senderEl.innerText.trim();
                        }

                        // Dedup por (timeText, sender)
                        const key = timeText + '|' + sender;
                        if (seen.has(key)) continue;
                        seen.add(key);

                        const isOut = !!msgContainer.closest('.message-out') ||
                                      msgContainer.classList.contains('message-out');
                        const prePlain = '[' + timeText + '] ' + (sender ? sender + ': ' : '');
                        msgs.push({ source: 'audio', idx: -1, prePlain, body: '[audio]', isOut });
                    }
                    return msgs;
                }
                """

            raw_msgs_text = await page.evaluate(_extract_text_msgs_js())
            logger.info(f"[{session_id}] scrape '{contact_name}': {len(raw_msgs_text)} msgs texto en DOM")

            # 3b. Scroll lento hacia abajo para forzar render de mensajes de voz.
            # WA Web virtualiza: los mensajes de texto (ya capturados) pueden desaparecer.
            # Mientras scrolleamos, capturamos audios (Part B) en cada paso.
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
                # Capturar audios visibles + descargar blob inline para PTT de grupos
                step_audios = await page.evaluate(_extract_audio_msgs_js())
                for a in step_audios:
                    key = a["prePlain"]
                    if key not in seen_audio_keys:
                        seen_audio_keys.add(key)
                        # Intentar descargar blob mientras está en DOM
                        if a.get("body") == "[audio]":
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

            logger.info(
                f"[{session_id}] scrape '{contact_name}': "
                f"scroll completo ({total_height}px), "
                f"{len(raw_msgs_audio)} msgs audio/voz encontrados"
            )

            # Combinar ambas partes
            raw_msgs = raw_msgs_text + raw_msgs_audio

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
                })

            logger.info(f"[{session_id}] scrape_full_history '{contact_name}': {len(parsed)} mensajes extraídos")

            # 5. Transcribir audios históricos (segundo pasaje: scroll al elemento, esperar blob)
            # Incluye [audio] (detectado en DOM) y [media] (vacío off-screen, puede ser audio)
            # Los mensajes de Parte B (source='audio', _raw_idx=-1) se guardan como [audio]
            # ya que el scroll lento ya los cargó — transcripción por índice no aplica.
            audio_entries = [(i, msg) for i, msg in enumerate(parsed) if msg["body"] in ("[audio]", "[media]")]
            if audio_entries:
                import os
                from tools import transcription as _transcription
                logger.info(f"[{session_id}] Transcribiendo {len(audio_entries)} audios históricos de '{contact_name}'...")
                for parsed_idx, msg in audio_entries:
                    pre_plain = msg.get("_pre_plain", "")
                    raw_idx = msg["_raw_idx"]
                    original_body = msg["body"]
                    # Mensajes de Parte B (sin data-pre-plain-text real) tienen idx=-1
                    # y prePlain manufacturado — el inline download debería haberlos captado.
                    # Si inline falló, no podemos hacer nada más por ellos.
                    if raw_idx == -1:
                        continue
                    # Parte A: buscar por data-pre-plain-text (robusto ante virtual DOM)
                    if not pre_plain:
                        continue
                    audio_path = await self._download_audio_blob_by_preplain(page, session_id, pre_plain)
                    if audio_path:
                        try:
                            text = await _transcription.transcribe(audio_path)
                            parsed[parsed_idx]["body"] = text
                            logger.info(f"[{session_id}] Audio histórico transcrito: {text[:60]}")
                        except Exception as exc:
                            parsed[parsed_idx]["body"] = "[audio — error al transcribir]"
                            logger.warning(f"[{session_id}] Error transcribiendo audio histórico: {exc}")
                        finally:
                            try:
                                os.unlink(audio_path)
                            except Exception:
                                pass
                    else:
                        if original_body == "[audio]":
                            parsed[parsed_idx]["body"] = "[audio — sin blob]"

            # Limpiar campos internos antes de retornar
            for msg in parsed:
                msg.pop("_raw_idx", None)
                msg.pop("_pre_plain", None)

            return parsed

        except Exception as e:
            logger.warning(f"[{session_id}] scrape_full_history error para '{contact_name}': {e}")
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

def _update(session_id: str, *, bot_id: str = "", status: str, qr: str | None = None) -> None:
    if session_id not in clients:
        clients[session_id] = {"bot_id": bot_id, "type": "whatsapp", "client": None, "qr": None}
    if bot_id:
        clients[session_id]["bot_id"] = bot_id
    clients[session_id]["status"] = status
    if qr is not None or status in ("connecting", "failed", "ready"):
        clients[session_id]["qr"] = qr
