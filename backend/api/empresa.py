"""Endpoints del portal de empresa — acceso con JWT Bearer token."""
import re
import logging
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks

logger = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy import text

from config import load_config, save_config
from state import clients
from db import AsyncSessionLocal, log_outbound_message
from middleware_auth import require_empresa_auth
import sim as sim_engine

router = APIRouter()


def _db_phone(number: str) -> str:
    """Telegram sessions usan session_id como key en clients pero guardan en DB solo el token_id."""
    # Formato: "{bot_id}-tg-{token_id}" → devuelve "{token_id}"
    if "-tg-" in number:
        return number.split("-tg-")[-1]
    return number


def _find_bot_by_password(config: dict, password: str):
    for bot in config.get("empresas", []):
        if bot.get("password") == password:
            return bot
    return None


def _require_empresa(bot_id: str, token_bot_id: str = Depends(require_empresa_auth)):
    """Verifica que el token JWT pertenezca al mismo bot_id del path."""
    if token_bot_id != bot_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta empresa")
    config = load_config()
    bot = next((b for b in config.get("empresas", []) if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return bot


def _generate_bot_id(name: str, config: dict) -> str:
    existing = {b["id"] for b in config.get("empresas", [])}
    base = re.sub(r"[^a-z0-9]+", "_", name.lower().strip()).strip("_") or "empresa"
    candidate = base
    i = 2
    while candidate in existing:
        candidate = f"{base}_{i}"
        i += 1
    return candidate


# ─── Auth ────────────────────────────────────────────────────────

class EmpresaAuthBody(BaseModel):
    password: str


@router.post("/empresa/auth")
def empresa_auth(body: EmpresaAuthBody):
    config = load_config()
    bot = _find_bot_by_password(config, body.password)
    if not bot:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    return {"ok": True, "bot_id": bot["id"], "bot_name": bot["name"]}


# ─── Dashboard ───────────────────────────────────────────────────

@router.get("/empresa/{bot_id}")
def empresa_get(bot_id: str, bot: dict = Depends(_require_empresa)):

    connections = []

    for phone in bot.get("phones", []):
        number = phone["number"]
        status = clients.get(number, {}).get("status", "stopped")
        connections.append({
            "id": number,
            "type": "whatsapp",
            "number": number,
            "status": status,
        })

    for tg in bot.get("telegram", []):
        token_id = tg["token"].split(":")[0]
        session_id = f"{bot['id']}-tg-{token_id}"
        status = clients.get(session_id, {}).get("status", "stopped")
        connections.append({
            "id": session_id,
            "type": "telegram",
            "number": session_id,
            "status": status,
        })

    return {
        "bot_id": bot["id"],
        "bot_name": bot["name"],
        "connections": connections,
    }


# ─── Connect / QR / Disconnect ───────────────────────────────────

@router.post("/empresa/{bot_id}/connect/{number}")
async def empresa_connect(bot_id: str, number: str, background_tasks: BackgroundTasks, bot: dict = Depends(_require_empresa)):

    if not any(p["number"] == number for p in bot.get("phones", [])):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

    existing = clients.get(number, {})
    if existing.get("status") in ("connecting", "qr_needed", "qr_ready", "ready"):
        return {"ok": True, "status": existing["status"], "sessionId": number}

    if sim_engine.SIM_MODE:
        sim_engine.sim_connect(number, bot_id)
        return {"ok": True, "status": "ready", "sessionId": number}

    from api.whatsapp import _connect_and_get_qr
    background_tasks.add_task(_connect_and_get_qr, number, bot_id)
    return {"ok": True, "status": "connecting", "sessionId": number}


@router.get("/empresa/{bot_id}/qr/{session_id}")
def empresa_qr(bot_id: str, session_id: str, _: dict = Depends(_require_empresa)):

    state = clients.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Sesión no iniciada")
    if state["status"] == "ready":
        return {"status": "ready"}
    if state.get("qr"):
        return {"status": state["status"], "qr": state["qr"]}
    return {"status": state["status"]}


@router.post("/empresa/{bot_id}/disconnect/{number}")
async def empresa_disconnect(bot_id: str, number: str, bot: dict = Depends(_require_empresa)):

    if not any(p["number"] == number for p in bot.get("phones", [])):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

    if sim_engine.SIM_MODE:
        sim_engine.sim_disconnect(number)
    else:
        from state import wa_session
        await wa_session.close_session(number)

    if number in clients:
        clients[number]["status"] = "disconnected"
        clients[number]["qr"] = None

    return {"ok": True}


# ─── Mensajes / Chat ─────────────────────────────────────────────

def _owns_session(bot: dict, session_id: str) -> bool:
    if any(p["number"] == session_id for p in bot.get("phones", [])):
        return True
    for tg in bot.get("telegram", []):
        token_id = tg["token"].split(":")[0]
        if f"{bot['id']}-tg-{token_id}" == session_id:
            return True
    return False


@router.get("/empresa/{bot_id}/messages/{number}")
async def empresa_messages(bot_id: str, number: str, bot: dict = Depends(_require_empresa)):
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered "
                "FROM messages WHERE connection_phone = :number AND outbound = 0 "
                "AND id IN ("
                "  SELECT MAX(id) FROM messages "
                "  WHERE connection_phone = :number AND outbound = 0 "
                "  GROUP BY phone"
                ") ORDER BY timestamp DESC"
            ),
            {"number": _db_phone(number)},
        )
        rows = result.fetchall()

    return [
        {"id": r[0], "phone": r[1], "name": r[2], "body": r[3],
         "timestamp": r[4], "answered": bool(r[5])}
        for r in rows
    ]


@router.get("/empresa/{bot_id}/chat/{number}/{contact}")
async def empresa_chat_get(bot_id: str, number: str, contact: str, bot: dict = Depends(_require_empresa)):
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, phone, name, body, timestamp, answered, outbound "
                "FROM messages WHERE connection_phone = :number AND phone = :contact "
                "ORDER BY timestamp ASC LIMIT 100"
            ),
            {"number": _db_phone(number), "contact": contact},
        )
        rows = result.fetchall()

    return [{"id": r[0], "phone": r[1], "name": r[2], "body": r[3],
             "timestamp": r[4], "answered": bool(r[5]), "outbound": bool(r[6])}
            for r in rows]


class EmpresaSendBody(BaseModel):
    text: str


@router.post("/empresa/{bot_id}/chat/{number}/{contact}")
async def empresa_chat_send(bot_id: str, number: str, contact: str,
                            body: EmpresaSendBody, bot: dict = Depends(_require_empresa)):
    if not _owns_session(bot, number):
        raise HTTPException(status_code=404, detail="Número no pertenece a esta empresa")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Texto vacío")

    db_number = _db_phone(number)

    if sim_engine.SIM_MODE:
        await log_outbound_message(bot_id, db_number, contact, body.text)
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE messages SET answered = 1 WHERE connection_phone = :number AND phone = :contact AND answered = 0"),
                {"number": db_number, "contact": contact},
            )
            await session.commit()
        return {"ok": True}

    if "-tg-" in number:
        tg_client = clients.get(number)
        if not tg_client:
            raise HTTPException(status_code=503, detail="Bot de Telegram no está activo")
        try:
            await tg_client["client"].bot.send_message(chat_id=int(contact), text=body.text)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"No se pudo enviar por Telegram: {e}")
    else:
        from state import wa_session
        ok = await wa_session.send_message(number, contact, body.text)
        if not ok:
            raise HTTPException(status_code=503, detail="No se pudo enviar. Verificá que el bot esté conectado.")

    await log_outbound_message(bot_id, db_number, contact, body.text)
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE messages SET answered = 1 WHERE connection_phone = :number AND phone = :contact AND answered = 0"),
            {"number": db_number, "contact": contact},
        )
        await session.commit()
    return {"ok": True}

# ─── Alta de empresa (sin auth) ──────────────────────────────────

class NuevaEmpresaBody(BaseModel):
    name: str
    password: str


@router.post("/empresa/nueva")
def empresa_nueva(body: NuevaEmpresaBody):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="El nombre es requerido")
    if not body.password.strip():
        raise HTTPException(status_code=400, detail="La contraseña es requerida")

    config = load_config()
    if _find_bot_by_password(config, body.password):
        raise HTTPException(status_code=409, detail="Esa contraseña ya está en uso")

    bot_id = _generate_bot_id(body.name, config)
    new_bot = {
        "id": bot_id,
        "name": body.name.strip(),
        "password": body.password,
        "phones": [],
        "telegram": [],
    }
    config["empresas"].append(new_bot)
    save_config(config)
    return {"ok": True, "bot_id": bot_id, "bot_name": new_bot["name"]}


# ─── Editar datos de la empresa ──────────────────────────────────

class EmpresaConfigBody(BaseModel):
    name: str | None = None
    password: str | None = None


@router.put("/empresa/{bot_id}/config")
def empresa_put_config(bot_id: str, body: EmpresaConfigBody, _: dict = Depends(_require_empresa)):

    config = load_config()
    bot = next((b for b in config["empresas"] if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(status_code=400, detail="Nombre no puede ser vacío")
        bot["name"] = body.name.strip()

    if body.password is not None:
        if not body.password.strip():
            raise HTTPException(status_code=400, detail="Contraseña no puede ser vacía")
        for b in config["empresas"]:
            if b["id"] != bot_id and b.get("password") == body.password:
                raise HTTPException(status_code=409, detail="Esa contraseña ya está en uso")
        bot["password"] = body.password

    save_config(config)
    return {"ok": True, "bot_id": bot_id, "bot_name": bot["name"]}


# ─── Gestión de conexiones WhatsApp ──────────────────────────────

class AddWhatsappBody(BaseModel):
    number: str


@router.post("/empresa/{bot_id}/whatsapp")
def empresa_add_whatsapp(bot_id: str, body: AddWhatsappBody, _: dict = Depends(_require_empresa)):
    number = body.number.strip()
    if not number:
        raise HTTPException(status_code=400, detail="Número requerido")

    config = load_config()
    bot = next(b for b in config["empresas"] if b["id"] == bot_id)
    if any(p["number"] == number for p in bot.get("phones", [])):
        raise HTTPException(status_code=409, detail=f"El número {number} ya está configurado en esta empresa")
    bot.setdefault("phones", []).append({"number": number})
    save_config(config)

    if sim_engine.SIM_MODE:
        sim_engine.sim_connect(number, bot_id)

    return {"ok": True, "number": number}


@router.delete("/empresa/{bot_id}/whatsapp/{number}")
async def empresa_remove_whatsapp(bot_id: str, number: str, _: dict = Depends(_require_empresa)):

    config = load_config()
    bot = next((b for b in config["empresas"] if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    original = len(bot.get("phones", []))
    bot["phones"] = [p for p in bot.get("phones", []) if p["number"] != number]
    if len(bot["phones"]) == original:
        raise HTTPException(status_code=404, detail="Número no encontrado")

    save_config(config)

    if sim_engine.SIM_MODE:
        sim_engine.sim_disconnect(number)
    else:
        from state import wa_session
        await wa_session.close_session(number)

    clients.pop(number, None)
    return {"ok": True}


# ─── Gestión de conexiones Telegram ──────────────────────────────

class AddTelegramBody(BaseModel):
    token: str


@router.post("/empresa/{bot_id}/telegram")
async def empresa_add_telegram(bot_id: str, body: AddTelegramBody, _: dict = Depends(_require_empresa)):
    token = body.token.strip()
    if not token or ":" not in token:
        raise HTTPException(status_code=400, detail="Token inválido (formato: 123456789:ABC...)")

    token_id = token.split(":")[0]
    session_id = f"{bot_id}-tg-{token_id}"

    config = load_config()
    for b in config["empresas"]:
        for tg in b.get("telegram", []):
            if tg["token"].split(":")[0] == token_id:
                raise HTTPException(status_code=409, detail="Ese token ya está configurado")

    bot = next(b for b in config["empresas"] if b["id"] == bot_id)
    bot.setdefault("telegram", []).append({"token": token})
    save_config(config)

    requires_restart = False
    if sim_engine.SIM_MODE:
        sim_engine.sim_connect(session_id, bot_id)
    else:
        # Intentar iniciar dinámicamente
        try:
            from bots.telegram_bot import build_telegram_app
            from main import _tg_apps
            cfg = {"connection_id": bot_id, "token": token}
            tg_app = build_telegram_app(cfg)
            await tg_app.initialize()
            await tg_app.start()
            await tg_app.updater.start_polling(drop_pending_updates=True)
            _tg_apps.append(tg_app)
            clients[session_id] = {"status": "ready", "qr": None, "connection_id": bot_id, "type": "telegram", "client": tg_app}
        except Exception:
            requires_restart = True

    return {"ok": True, "session_id": session_id, "requires_restart": requires_restart}


@router.delete("/empresa/{bot_id}/telegram/{token_id}")
def empresa_remove_telegram(bot_id: str, token_id: str, _: dict = Depends(_require_empresa)):

    config = load_config()
    bot = next((b for b in config["empresas"] if b["id"] == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    original = len(bot.get("telegram", []))
    bot["telegram"] = [tg for tg in bot.get("telegram", []) if tg["token"].split(":")[0] != token_id]
    if len(bot["telegram"]) == original:
        raise HTTPException(status_code=404, detail="Token no encontrado")

    save_config(config)
    session_id = f"{bot_id}-tg-{token_id}"
    if sim_engine.SIM_MODE:
        sim_engine.sim_disconnect(session_id)
    clients.pop(session_id, None)
    return {"ok": True}


_COLLECT_CONTACTS_JS = """
() => {
    function looksLikePhone(s) {
        return /^[\\+\\d][\\d\\s\\-\\.\\(\\)]{5,}$/.test(s.trim());
    }
    function normalizePhone(s) {
        return s.replace(/\\D/g, '');
    }
    const BAD_PREFIXES = ['Esperando', 'Hola! Estoy', '¡Hola! Estoy', 'Disponible',
                          'Hey there', 'Busy', 'Foto', 'Sticker', 'Audio', 'Video',
                          'GIF', 'Documento', 'Ubicación', 'Contacto compartido',
                          'WhatsApp', 'Seguridad', 'Cifrado'];
    function isJunk(s) {
        if (!s || s.length === 0 || s.length >= 80) return true;
        if (/^\\d+:\\d+$/.test(s.trim())) return true;  // duración audio
        return BAD_PREFIXES.some(f => s.includes(f));
    }

    const spans = Array.from(document.querySelectorAll('span[title]'));
    const seen = {};  // name → phone (phone puede ser null)

    for (let i = 0; i < spans.length; i++) {
        const t = (spans[i].getAttribute('title') || '').trim();
        if (isJunk(t)) continue;

        if (looksLikePhone(t)) {
            // Es un teléfono — buscar nombre adyacente
            const phone = normalizePhone(t);
            if (phone.length < 7 || phone.length > 15) continue;
            let name = null;
            for (let d = -3; d <= 3; d++) {
                if (d === 0) continue;
                const j = i + d;
                if (j < 0 || j >= spans.length) continue;
                const candidate = (spans[j].getAttribute('title') || '').trim();
                if (!isJunk(candidate) && !looksLikePhone(candidate)) { name = candidate; break; }
            }
            const key = name || phone;
            if (!seen[key]) seen[key] = { name: name || phone, phone };
        } else {
            // Es un nombre — registrar aunque no tengamos el teléfono
            if (!seen[t]) seen[t] = { name: t, phone: null };
        }
    }
    return Object.values(seen);
}
"""

_FIND_SCROLLABLE_JS = """
(panelSelector) => {
    const root = panelSelector ? document.querySelector(panelSelector) : document.body;
    if (!root) return null;
    for (const el of root.querySelectorAll('*')) {
        const s = window.getComputedStyle(el);
        if ((s.overflowY === 'scroll' || s.overflowY === 'auto') && el.scrollHeight > el.clientHeight + 20) {
            return el;
        }
    }
    return null;
}
"""


async def _scrape_wa_contacts(page) -> list[dict]:
    """
    Abre el panel 'Nuevo chat' de WA Web, scrollea la lista de contactos
    de la agenda completa, los recolecta y cierra el panel.
    Devuelve lista de {phone, name}.
    """
    import asyncio

    # 1. Abrir panel "Nuevo chat"
    new_chat_btn = (
        page.locator('[data-testid="new-chat-btn"]').first
        or page.locator('[aria-label="Nuevo chat"]').first
        or page.locator('[aria-label="New chat"]').first
    )
    # Intentar con distintos selectores
    for sel in ['[data-testid="new-chat-btn"]', '[aria-label="Nuevo chat"]',
                '[aria-label="New chat"]', '[title="Nuevo chat"]']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1000):
                await btn.click()
                break
        except Exception:
            continue
    else:
        logger.warning("[import-wa] No se encontró el botón 'Nuevo chat'")
        return []

    await asyncio.sleep(1.0)  # esperar que cargue el panel

    # Diagnóstico: ver qué estructura tiene el panel recién abierto
    diag = await page.evaluate("""
    () => {
        const withDataId = document.querySelectorAll('[data-id]');
        const sample = Array.from(withDataId).slice(0, 5).map(el => ({
            tag: el.tagName, data_id: el.getAttribute('data-id')
        }));
        // Ver elementos con título
        const withTitle = document.querySelectorAll('[title]');
        const sampleTitle = Array.from(withTitle).slice(0, 5).map(el => ({
            tag: el.tagName, title: el.getAttribute('title'), cls: el.className.slice(0,40)
        }));
        // Ver roles de lista
        const listItems = document.querySelectorAll('[role="listitem"], [role="option"], [role="row"]');
        return {
            data_id_count: withDataId.length,
            data_id_sample: sample,
            title_sample: sampleTitle,
            list_items: listItems.length,
            list_item_sample: Array.from(listItems).slice(0, 3).map(el => ({
                tag: el.tagName,
                role: el.getAttribute('role'),
                html: el.innerHTML.slice(0, 150),
            })),
        };
    }
    """)
    logger.info("[import-wa] panel diagnóstico: %s", diag)

    # 2. Buscar el contenedor scrolleable del panel de contactos
    scroll_handle = await page.evaluate_handle(_FIND_SCROLLABLE_JS, '#app')
    if not scroll_handle:
        logger.warning("[import-wa] No se encontró el scrollable en el panel de contactos")
        await page.keyboard.press("Escape")
        return []

    # clave: name si existe, sino phone. Así los contactos sin teléfono no colapsan en None.
    seen: dict[str, dict] = {}

    async def collect():
        contacts = await page.evaluate(_COLLECT_CONTACTS_JS)
        for c in contacts:
            key = c.get("name") or c.get("phone")
            if not key:
                continue
            if key not in seen:
                seen[key] = c
            elif c.get("phone") and not seen[key].get("phone"):
                # Tenemos nombre registrado sin phone — actualizamos si ahora tenemos el número
                seen[key]["phone"] = c["phone"]

    await collect()

    # 3. Scrollear hasta el final recolectando en cada paso
    last_top = -1
    stuck = 0
    while stuck < 3:
        await page.evaluate("(el) => { el.scrollTop += el.clientHeight * 0.8; }", scroll_handle)
        await asyncio.sleep(0.4)
        await collect()
        top = await page.evaluate("(el) => el.scrollTop", scroll_handle)
        if top == last_top:
            stuck += 1
        else:
            stuck = 0
            last_top = top

    # 4. Cerrar el panel
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass

    return list(seen.values())


@router.get("/empresa/{bot_id}/debug-wa-sidebar/{number}")
async def empresa_debug_wa_sidebar(
    bot_id: str, number: str,
    _: dict = Depends(_require_empresa),
):
    """Debug: devuelve lo que el JS encuentra en el sidebar sin escribir nada en la DB."""
    session = clients.get(number)
    if not session or session.get("status") != "ready":
        raise HTTPException(400, "El número no está conectado")
    if session.get("connection_id") != bot_id:
        raise HTTPException(403, "El número no pertenece a esta empresa")
    from state import wa_session
    page = wa_session._pages.get(number)
    if page is None or page.is_closed():
        raise HTTPException(400, "No hay página WA activa para ese número")
    # Diagnóstico del DOM para entender la estructura real de WA Web
    diag = await page.evaluate("""
    () => {
        const info = {};
        // IDs de contenedores conocidos
        info.has_pane_side  = !!document.getElementById('pane-side');
        info.has_side       = !!document.getElementById('side');
        info.has_app        = !!document.getElementById('app');
        info.url            = location.href;
        info.title          = document.title;
        // Buscar cualquier elemento con data-id
        const withDataId = document.querySelectorAll('[data-id]');
        info.data_id_count  = withDataId.length;
        info.data_id_sample = Array.from(withDataId).slice(0, 5).map(el => ({
            tag: el.tagName,
            data_id: el.getAttribute('data-id'),
        }));
        // Buscar scrollable
        const all = document.querySelectorAll('*');
        const scrollables = [];
        for (const el of all) {
            const s = window.getComputedStyle(el);
            if ((s.overflowY === 'scroll' || s.overflowY === 'auto') && el.scrollHeight > el.clientHeight + 10) {
                scrollables.push({ tag: el.tagName, id: el.id, cls: el.className.slice(0, 60), scrollHeight: el.scrollHeight });
            }
        }
        info.scrollables = scrollables.slice(0, 5);
        // HTML completo del primer listitem con nombre (para ver si tiene teléfono escondido)
        const listitems = document.querySelectorAll('[role="listitem"]');
        info.listitem_full_html = Array.from(listitems).slice(0, 3).map(el => el.innerHTML);
        // Buscar cualquier texto que parezca teléfono en el DOM completo
        const phoneRe = /\+?54\s*9?\s*\d[\d\s\-]{8,}/g;
        info.phone_texts_in_dom = [];
        for (const el of document.querySelectorAll('span, div')) {
            const t = (el.textContent || '').trim();
            if (phoneRe.test(t) && t.length < 30) {
                info.phone_texts_in_dom.push({ tag: el.tagName, text: t, cls: el.className.slice(0,40) });
                if (info.phone_texts_in_dom.length >= 10) break;
            }
        }
        return info;
    }
    """)
    chats = await _scrape_wa_contacts(page)
    return {"found": len(chats), "sample": chats[:10], "diag": diag}


@router.post("/empresa/{bot_id}/import-wa-contacts/{number}")
async def empresa_import_wa_contacts(
    bot_id: str, number: str,
    _: dict = Depends(_require_empresa),
):
    """
    Combina dos fuentes para poblar sugeridos:
    1. WA Web DOM scraping (contactos no guardados con teléfono visible)
    2. Historial de mensajes en DB (contactos que ya enviaron mensajes con número real)

    Los resultados se insertan como mensajes dummy [wa-contact-import].
    """
    session = clients.get(number)
    if not session or session.get("status") != "ready":
        raise HTTPException(400, "El número no está conectado")

    # Seguridad: verificar que este número pertenece al bot_id solicitado
    if session.get("connection_id") != bot_id:
        raise HTTPException(403, "El número no pertenece a esta empresa")

    # Fuente 1: WA Web DOM scraping
    wa_chats: list[dict] = []
    from state import wa_session
    page = wa_session._pages.get(number)
    if page is not None and not page.is_closed():
        wa_chats = await _scrape_wa_contacts(page)
        logger.info("[import-wa] WA scraping: %d contactos para %s", len(wa_chats), number)

    # Fuente 2: historial de mensajes con teléfonos reales (solo dígitos, 7-15 chars)
    db_chats: list[dict] = []
    async with AsyncSessionLocal() as db_session:
        rows = (await db_session.execute(
            text("""
                SELECT phone, MAX(name) as name
                FROM messages
                WHERE connection_id = :bid
                  AND body != '[wa-contact-import]'
                  AND outbound = 0
                  AND length(phone) BETWEEN 7 AND 15
                  AND phone NOT GLOB '*[^0-9]*'
                GROUP BY phone
                ORDER BY name
            """),
            {"bid": bot_id},
        )).fetchall()
    for row in rows:
        db_chats.append({"phone": row[0], "name": row[1] or row[0]})
    logger.info("[import-wa] DB history: %d contactos con teléfono real", len(db_chats))

    # Merge: clave = name si existe, sino phone. WA scraping tiene prioridad.
    merged: dict[str, dict] = {}
    for c in db_chats:
        key = c["name"] or c["phone"]
        if key and key not in merged:
            merged[key] = c
    for c in wa_chats:
        key = c["name"] or c["phone"]
        if key:
            merged[key] = c  # WA override

    all_contacts = list(merged.values())
    logger.info("[import-wa] total combinado: %d contactos únicos", len(all_contacts))

    if not all_contacts:
        return {"imported": 0, "message": "No se encontraron contactos"}

    imported = 0
    async with AsyncSessionLocal() as db_session:
        for c in all_contacts:
            name  = c.get("name") or None
            phone = c.get("phone") or None
            if not name and not phone:
                continue
            try:
                await db_session.execute(
                    text("""INSERT OR IGNORE INTO contact_suggestions
                            (empresa_id, name, phone, source)
                            VALUES (:eid, :name, :phone, 'wa_import')"""),
                    {"eid": bot_id, "name": name, "phone": phone},
                )
                imported += 1
            except Exception:
                pass
        await db_session.commit()

    return {
        "imported": imported,
        "total_wa_scraping": len(wa_chats),
        "total_db_history": len(db_chats),
        "total_combined": len(all_contacts),
    }


@router.delete("/empresa/{bot_id}/suggested-contacts")
async def empresa_clear_suggested_contacts(
    bot_id: str,
    _: dict = Depends(_require_empresa),
):
    """Limpia todas las contact_suggestions de esta empresa."""
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            text("DELETE FROM contact_suggestions WHERE empresa_id = :bid"),
            {"bid": bot_id},
        )
        await db_session.commit()
    return {"deleted": result.rowcount}


@router.delete("/empresa/{bot_id}/suggested-contacts/{name}")
async def empresa_delete_one_suggestion(
    bot_id: str,
    name: str,
    _: dict = Depends(_require_empresa),
):
    """Elimina una sugerencia específica por nombre."""
    async with AsyncSessionLocal() as db_session:
        await db_session.execute(
            text("DELETE FROM contact_suggestions WHERE empresa_id = :bid AND name = :name"),
            {"bid": bot_id, "name": name},
        )
        await db_session.commit()
    return {"ok": True}
