"""
Router: /flows

Thin FastAPI wrapper over the business layer. No auth — auth is applied
by interfaces/ui/app.py at mount time.

Route mapping (parent mounts at /flows):
  GET  /node-types
  GET  /google-accounts
  POST /clear-sheet-cache
  GET  /bots/{bot_id}
  POST /bots/{bot_id}
  GET  /bots/{bot_id}/{flow_id}
  PUT  /bots/{bot_id}/{flow_id}
  DELETE /bots/{bot_id}/{flow_id}
  GET  /bots/{bot_id}/has-node/{node_type}
  POST /bots/{bot_id}/{flow_id}/replay
  POST /{flow_id}/trigger/{node_id}
  GET  /bots/{bot_id}/google-accounts
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from pulpo.business import flows as flows_svc

_log = logging.getLogger(__name__)

router = APIRouter()


# ─── Node type catalogue ──────────────────────────────────────────────────────

@router.get("/node-types")
def list_node_types():
    """
    Catálogo de tipos de nodo: id, label, color, description, schema.
    schema es una lista ordenada de campos para que el frontend renderice
    el panel de configuración sin hardcodear nada.
    """
    try:
        return flows_svc.list_node_types()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Google accounts (global, env-based) ─────────────────────────────────────

@router.get("/google-accounts")
def list_google_accounts():
    """
    Devuelve las cuentas de servicio Google configuradas vía env var.
    Retorna [{id, email, label}] para poblar el selector en el frontend.
    """
    try:
        return flows_svc.list_google_accounts()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Sheet cache ──────────────────────────────────────────────────────────────

@router.post("/clear-sheet-cache")
def clear_sheet_cache():
    """Limpia el caché en memoria de fetch_sheet, search_sheet y gsheet."""
    try:
        return flows_svc.clear_sheet_cache()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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


# ─── CRUD ────────────────────────────────────────────────────────────────────

@router.get("/bots/{bot_id}")
async def list_flows(bot_id: str):
    try:
        return await flows_svc.list_flows(bot_id=bot_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/bots/{bot_id}", status_code=201)
async def create_flow(bot_id: str, body: FlowIn):
    try:
        return await flows_svc.create_flow(
            bot_id=bot_id,
            name=body.name,
            definition=body.definition,
            connection_id=body.connection_id,
            contact_phone=body.contact_phone,
            contact_filter=body.contact_filter,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bots/{bot_id}/has-node/{node_type}")
async def has_node_type(bot_id: str, node_type: str):
    """Devuelve {found: bool} indicando si algún flow de la bot contiene el tipo de nodo."""
    try:
        found = await flows_svc.has_node_type(bot_id=bot_id, node_type=node_type)
        return {"found": found}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/bots/{bot_id}/{flow_id}")
async def get_flow(bot_id: str, flow_id: str):
    flow = await flows_svc.get_flow(bot_id=bot_id, flow_id=flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow no encontrado")
    return flow


@router.put("/bots/{bot_id}/{flow_id}")
async def update_flow(bot_id: str, flow_id: str, body: FlowUpdate):
    try:
        result = await flows_svc.update_flow(
            bot_id=bot_id,
            flow_id=flow_id,
            updates=body.model_dump(exclude_none=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Flow no encontrado")
    return result


@router.post("/bots/{bot_id}/{flow_id}/replay")
async def replay_flow(
    bot_id: str,
    flow_id: str,
    from_date: Optional[str] = None,
):
    """
    Ejecuta el flow completo para cada mensaje histórico de la DB.
    Los nodos reply/llm no envían nada real (from_delta_sync=True).

    from_date (YYYY-MM-DD): si se pasa, solo procesa mensajes desde esa fecha.
    """
    try:
        return await flows_svc.replay_flow(
            bot_id=bot_id,
            flow_id=flow_id,
            from_date=from_date,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/bots/{bot_id}/{flow_id}", status_code=204)
async def delete_flow(bot_id: str, flow_id: str):
    ok = await flows_svc.delete_flow(bot_id=bot_id, flow_id=flow_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Flow no encontrado")
    return Response(status_code=204)


@router.get("/bots/{bot_id}/google-accounts")
async def list_bot_google_accounts(bot_id: str):
    """Lista las cuentas Google disponibles para la bot (propias + pulpo-default)."""
    try:
        return await flows_svc.list_bot_google_accounts(bot_id=bot_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── API trigger ──────────────────────────────────────────────────────────────

class ApiTriggerBody(BaseModel):
    message: str = ""
    contact_phone: str = "api"
    contact_name: str = "API"


_DEFAULT_FAREWELL = (
    "¡Hola! 👋 Tu consulta anterior se cerró porque pasó un tiempo sin actividad "
    "— ¡pero no te preocupes, acá seguimos!\n\n"
    "En Luganense conectamos vecinos con los mejores profesionales de la zona: "
    "plomeros, electricistas, albañiles, pintores y muchos servicios más. "
    "Todos confiables, todos cerca tuyo.\n\n"
    "Cuando necesités algo, escribinos y te ayudamos en segundos. 🏠✨\n\n"
    "¡Hasta la próxima!\n— Luganense"
)


@router.post("/conversations/expire")
async def expire_conversations(
    max_age_hours: int = 24,
    farewell: str | None = None,
):
    """Expira conversaciones en waiting_gate más viejas que max_age_hours.
    Si farewell no es 'no', manda un mensaje de despedida a cada contacto expirado."""
    from pulpo.core import db as _db
    expired = await _db.expire_old_conversations(max_age_hours)
    count = len(expired)

    send_farewell = farewell != "no"
    if send_farewell and expired:
        from pulpo.core.state import clients
        from pulpo.core.config import load_config
        import logging
        _log = logging.getLogger(__name__)
        bot_config_cache: dict[str, dict] = {}
        try:
            cfg = load_config()
            bot_config_cache = {b["id"]: b for b in cfg.get("bots", [])}
        except Exception:
            pass
        for item in expired:
            bot_id = item["bot_id"]
            contact = item["contact_phone"]
            bot_cfg = bot_config_cache.get(bot_id, {})
            farewell_text = (
                farewell if farewell and farewell not in ("yes", "no")
                else bot_cfg.get("farewell_message") or _DEFAULT_FAREWELL
            )
            tg_session = next(
                (k for k, v in clients.items()
                 if v.get("connection_id") == bot_id
                 and v.get("type") == "telegram"
                 and v.get("client")),
                None,
            )
            if not tg_session:
                _log.warning("[expire] Sin bot TG activo para bot='%s' contact='%s' — skip farewell", bot_id, contact)
                continue
            bot = clients[tg_session]["client"].bot
            try:
                await bot.send_message(chat_id=int(contact), text=farewell_text)
                _log.info("[expire] farewell → bot=%s contact=%s", bot_id, contact)
            except Exception as e:
                _log.warning("[expire] Error farewell → %s: %s", contact, e)

    return {"expired": count, "max_age_hours": max_age_hours}


@router.post("/{flow_id}/trigger/{node_id}")
async def trigger_flow(flow_id: str, node_id: str, body: ApiTriggerBody = None):
    """
    Dispara un flow desde un nodo api_trigger específico.
    Retorna {ok: true, reply: "..."} o {ok: true, reply: null}.
    """
    if body is None:
        body = ApiTriggerBody()
    try:
        return await flows_svc.trigger_flow(
            flow_id=flow_id,
            node_id=node_id,
            message=body.message,
            contact_phone=body.contact_phone,
            contact_name=body.contact_name,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
