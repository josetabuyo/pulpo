"""
API REST de flows (grafos de agente).

GET    /api/flow/node-types                      → catálogo de tipos de nodo (público)
GET    /api/empresas/{id}/flows                  → lista de flows de la empresa (auth)
POST   /api/empresas/{id}/flows                  → crear flow (auth)
GET    /api/empresas/{id}/flows/{flow_id}        → detalle con definition (auth)
PUT    /api/empresas/{id}/flows/{flow_id}        → actualizar (auth)
DELETE /api/empresas/{id}/flows/{flow_id}        → eliminar (auth)
"""
import os
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi import Header
from pydantic import BaseModel
from typing import Optional

_log = logging.getLogger(__name__)

import db
from config import load_config
from middleware_auth import get_empresa_id_from_token
from graphs.node_types import NODE_TYPES
from graphs.nodes import NODE_REGISTRY

router = APIRouter()

_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# ─── Auth helpers ─────────────────────────────────────────────────────────────

def _require_empresa(empresa_id: str, request: Request, x_password: Optional[str]) -> dict:
    config = load_config()
    bot = next((b for b in config.get("empresas", []) if b["id"] == empresa_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    if x_password and x_password == _ADMIN_PASSWORD:
        return bot
    token_empresa_id = get_empresa_id_from_token(request)
    if not token_empresa_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    if token_empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta empresa")
    return bot


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/flow/node-types")
def list_node_types():
    """
    Catálogo de tipos de nodo: id, label, color, description, schema.
    schema es una lista ordenada de campos: [{key, type, label, default?, hint?, rows?, required?, options?, show_if?}]
    El frontend lo usa para renderizar el panel de configuración sin hardcodear nada.
    """
    result = []
    for nt in NODE_TYPES.values():
        node_class = NODE_REGISTRY.get(nt.id)
        schema_dict = node_class.config_schema() if node_class else {}
        schema = [{"key": k, **v} for k, v in schema_dict.items()]
        # Primer párrafo del docstring de la clase (sin los Config: detallados)
        raw_doc = (node_class.__doc__ or '').strip() if node_class else ''
        help_text = raw_doc.split('\n\nConfig:')[0].strip() if raw_doc else ''
        result.append({
            "id":          nt.id,
            "label":       nt.label,
            "color":       nt.color,
            "description": nt.description,
            "help":        help_text,
            "schema":      schema,
        })
    return result


# ─── Schemas ─────────────────────────────────────────────────────────────────

class FlowIn(BaseModel):
    name: str
    definition: dict | None = None
    connection_id: str | None = None
    contact_phone: str | None = None
    contact_filter: dict | None = None


class FlowUpdate(BaseModel):
    name: str | None = None
    definition: dict | None = None
    connection_id: str | None = None
    contact_phone: str | None = None
    contact_filter: dict | None = None
    active: bool | None = None


# ─── Cuentas Google configuradas ─────────────────────────────────────────────

@router.get("/flow/google-accounts")
def list_google_accounts():
    """
    Devuelve las cuentas de servicio Google configuradas.
    Por ahora soporta una sola cuenta via GOOGLE_SERVICE_ACCOUNT_JSON.
    Retorna [{id, email, label}] para poblar el selector en el frontend.
    """
    import json as _json
    accounts = []
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if sa_json:
        try:
            d = _json.loads(sa_json)
            accounts.append({
                "id":    "default",
                "email": d.get("client_email", ""),
                "label": "Cuenta principal",
            })
        except Exception:
            pass
    return accounts


# ─── Caché de nodos sheet ────────────────────────────────────────────────────

@router.post("/flow/clear-sheet-cache")
def clear_sheet_cache():
    """Limpia el caché en memoria de fetch_sheet, search_sheet y gsheet."""
    from graphs.nodes.fetch_sheet import _sheet_cache
    from graphs.nodes.search_sheet import _rows_cache as _search_cache
    from graphs.nodes.gsheet import _rows_cache as _gsheet_cache
    n = len(_sheet_cache) + len(_search_cache) + len(_gsheet_cache)
    _sheet_cache.clear()
    _search_cache.clear()
    _gsheet_cache.clear()
    return {"ok": True, "cleared": n}


# ─── Endpoints de flows CRUD ──────────────────────────────────────────────────

@router.get("/empresas/{empresa_id}/flows")
async def list_flows(
    empresa_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_empresa(empresa_id, request, x_password)
    return await db.get_flows(empresa_id)


@router.post("/empresas/{empresa_id}/flows", status_code=201)
async def create_flow(
    empresa_id: str,
    body: FlowIn,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_empresa(empresa_id, request, x_password)
    try:
        flow_id = await db.create_flow(
            empresa_id=empresa_id,
            name=body.name,
            definition=body.definition,
            connection_id=body.connection_id,
            contact_phone=body.contact_phone,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await db.get_flow(flow_id)


@router.get("/empresas/{empresa_id}/flows/{flow_id}")
async def get_flow(
    empresa_id: str,
    flow_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_empresa(empresa_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["empresa_id"] != empresa_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")
    return flow


@router.put("/empresas/{empresa_id}/flows/{flow_id}")
async def update_flow(
    empresa_id: str,
    flow_id: str,
    body: FlowUpdate,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_empresa(empresa_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["empresa_id"] != empresa_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")
    updates = body.model_dump(exclude_none=True)

    # Inyectar connection_id y contact_filter en el nodo message_trigger de la definition.
    # El compiler lee estos valores desde el config del nodo, no desde el registro del flow.
    if "definition" in updates:
        definition = updates["definition"]
        new_conn = updates.get("connection_id")
        new_cf   = updates.get("contact_filter")
        for node in definition.get("nodes", []):
            if node.get("type") == "message_trigger":
                cfg = node.setdefault("config", {})
                if new_conn is not None:
                    cfg["connection_id"] = new_conn
                if new_cf is not None:
                    cfg["contact_filter"] = new_cf
                break

    if updates:
        await db.update_flow(flow_id, **updates)
    return await db.get_flow(flow_id)


@router.get("/empresas/{empresa_id}/flows/has-node/{node_type}")
async def has_node_type(
    empresa_id: str,
    node_type: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    """Devuelve {found: bool} indicando si algún flow de la empresa contiene el tipo de nodo."""
    _require_empresa(empresa_id, request, x_password)
    found = await db.empresa_has_node_type(empresa_id, node_type)
    return {"found": found}


@router.post("/empresas/{empresa_id}/flows/{flow_id}/replay")
async def replay_flow(
    empresa_id: str,
    flow_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
    from_date: Optional[str] = None,
):
    """
    Ejecuta el flow completo para cada mensaje de la DB (from_delta_sync=True,
    los nodos reply/llm no envían nada real).

    from_date (YYYY-MM-DD): si se pasa, solo procesa mensajes desde esa fecha.
    Solo aplica a flows con trigger whatsapp_trigger o telegram_trigger.
    """
    _require_empresa(empresa_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["empresa_id"] != empresa_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")

    # Encontrar el nodo trigger y su connection_id + canal
    nodes = flow.get("definition", {}).get("nodes", [])
    trigger = next(
        (n for n in nodes if n.get("type") in ("whatsapp_trigger", "telegram_trigger", "message_trigger")),
        None,
    )
    if not trigger:
        raise HTTPException(status_code=400, detail="El flow no tiene un nodo trigger de mensajes")

    trigger_type = trigger.get("type", "")
    connection_id = trigger.get("config", {}).get("connection_id", "")
    if not connection_id:
        raise HTTPException(status_code=400, detail="El trigger no tiene connection_id configurado")

    canal = "telegram" if trigger_type == "telegram_trigger" else "whatsapp"

    date_filter = ""
    date_params: dict = {}
    if from_date:
        date_filter = " AND timestamp >= :from_date"
        date_params["from_date"] = from_date

    # Los mensajes pueden estar guardados bajo el número WA (connection_id)
    # o bajo el empresa_id. Probamos ambos y usamos el que tenga datos.
    from db import AsyncSessionLocal, text as _text
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            _text(
                f"SELECT phone, name, body, timestamp FROM messages "
                f"WHERE connection_id = :cid AND outbound = 0{date_filter} "
                f"ORDER BY timestamp ASC"
            ),
            {"cid": connection_id, **date_params},
        )).fetchall()
        if not rows:
            rows = (await session.execute(
                _text(
                    f"SELECT phone, name, body, timestamp FROM messages "
                    f"WHERE connection_id = :eid AND outbound = 0{date_filter} "
                    f"ORDER BY timestamp ASC"
                ),
                {"eid": empresa_id, **date_params},
            )).fetchall()

    if not rows:
        return {"processed": 0, "skipped": 0}

    from graphs.compiler import execute_flow
    from graphs.nodes.state import FlowState
    from datetime import datetime as _dt

    processed = 0
    skipped = 0

    for phone, name, body, ts_raw in rows:
        if not body or not body.strip():
            skipped += 1
            continue

        ts = None
        try:
            ts = _dt.fromisoformat(str(ts_raw))
        except (ValueError, TypeError):
            pass

        state = FlowState(
            message=body.strip(),
            message_type="text",
            connection_id=connection_id,
            canal=canal,
            empresa_id=empresa_id,
            contact_phone=phone,
            contact_name=name or phone,
            from_delta_sync=True,
            timestamp=ts,
        )
        await execute_flow(flow, state)
        processed += 1

    return {"processed": processed, "skipped": skipped}


@router.post("/empresas/{empresa_id}/flows/{flow_id}/import-wa-history")
async def import_wa_history(
    empresa_id: str,
    flow_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    """
    Raspa el historial completo de WA para cada contacto en el filtro del trigger
    y acumula directamente en el .md del summarizer.
    Limpia el .md existente antes de acumular (full resync).
    Corre en background — responde inmediatamente.
    """
    _require_empresa(empresa_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["empresa_id"] != empresa_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")

    nodes = flow.get("definition", {}).get("nodes", [])
    trigger = next(
        (n for n in nodes if n.get("type") in ("whatsapp_trigger", "telegram_trigger", "message_trigger")),
        None,
    )
    if not trigger or trigger.get("type") != "whatsapp_trigger":
        raise HTTPException(status_code=400, detail="El flow no tiene un whatsapp_trigger")

    trigger_config = trigger.get("config", {})
    connection_id = trigger_config.get("connection_id", "")
    contact_filter = trigger_config.get("contact_filter", {})
    included = contact_filter.get("included", [])
    if not included:
        raise HTTPException(status_code=400, detail="El trigger no tiene contactos en la lista de inclusión")

    from_date: Optional[str] = request.query_params.get("from_date")

    async def _do_import():
        from state import wa_session, clients
        from graphs.nodes.summarize import (
            accumulate as _accumulate,
            get_attachments_dir as _get_att_dir,
        )
        from datetime import datetime as _dt

        # Buscar sesión WA activa por connection_id del trigger (funciona con sesiones compartidas)
        session_id = connection_id if connection_id in clients and clients[connection_id].get("status") == "ready" else None
        if not session_id:
            # Fallback: cualquier sesión lista
            for bot_phone, client in clients.items():
                if client.get("status") == "ready" and client.get("type") == "whatsapp":
                    session_id = bot_phone
                    break
        if not session_id or not wa_session:
            _log.error("[import-wa] Sin sesión WA lista (connection_id=%s empresa=%s)", connection_id, empresa_id)
            return

        stop_before_ts = None
        if from_date:
            try:
                stop_before_ts = _dt.fromisoformat(from_date)
            except ValueError:
                pass

        for contact_name in included:
            _log.info("[import-wa] Importando historial de '%s' (empresa=%s, desde=%s)", contact_name, empresa_id, from_date or "inicio")
            try:
                contact_phone = contact_name
                doc_dir = _get_att_dir(empresa_id, contact_phone)
                messages = await wa_session.scrape_full_history_v2(
                    session_id, contact_name,
                    doc_save_dir=doc_dir,
                    stop_before_ts=stop_before_ts,
                    max_scroll_rounds=500,
                )
                messages.sort(key=lambda m: m.get("timestamp") or "")
                saved = 0
                for msg in messages:
                    body = msg.get("body", "")
                    sender = msg.get("sender")
                    if sender:
                        body = f"{sender}: {body}"
                    if not body.strip():
                        continue
                    ts = None
                    try:
                        ts = _dt.strptime(msg["timestamp"], "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass
                    _accumulate(
                        empresa_id=empresa_id,
                        contact_phone=contact_phone,
                        contact_name=contact_name,
                        msg_type=msg.get("msg_type", "text"),
                        content=body.strip(),
                        timestamp=ts,
                    )
                    saved += 1
                _log.info("[import-wa] '%s': %d mensajes importados", contact_name, saved)
            except Exception as e:
                _log.error("[import-wa] Error para '%s': %s", contact_name, e)

    background_tasks.add_task(_do_import)
    return {"status": "started", "contacts": included}


@router.delete("/empresas/{empresa_id}/flows/{flow_id}", status_code=204)
async def delete_flow(
    empresa_id: str,
    flow_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    _require_empresa(empresa_id, request, x_password)
    flow = await db.get_flow(flow_id)
    if not flow or flow["empresa_id"] != empresa_id:
        raise HTTPException(status_code=404, detail="Flow no encontrado")
    await db.delete_flow(flow_id)
    return Response(status_code=204)


@router.get("/empresas/{empresa_id}/google-accounts")
async def list_google_accounts(
    empresa_id: str,
    request: Request,
    x_password: Optional[str] = Header(None),
):
    """Lista las cuentas Google disponibles para la empresa (propias + pulpo-default)."""
    _require_empresa(empresa_id, request, x_password)
    conns = await db.get_google_connections(empresa_id)
    return [{"id": c["id"], "email": c["email"], "label": c["label"]} for c in conns]


# ─── Seed de flows por defecto ────────────────────────────────────────────────

_DEFAULT_FLOW_DEFINITION = {
    "nodes": [
        {"id": "message_trigger_1", "type": "message_trigger", "position": {"x": 250, "y": 50}, "config": {}},
    ],
    "edges": [],
    "viewport": {"x": 0, "y": 0, "zoom": 1},
}


async def seed_default_flows():
    """
    Si un bot no tiene flow, NO crea uno automáticamente.
    Un flow requiere connection_id explícito — no se puede inferir de forma segura.
    El usuario debe crear el flow desde el editor y asignarle una conexión.
    """
    pass
