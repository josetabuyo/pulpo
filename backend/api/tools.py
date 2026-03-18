"""
API REST de herramientas.
empresa_id == bot_id del bot en phones.json.
Las conexiones de una empresa son sus números WA + session_ids TG.
"""
import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text

import db
from db import AsyncSessionLocal
from config import load_config
from middleware_auth import require_empresa_auth

router = APIRouter()


# ─── Auth empresa ────────────────────────────────────────────────

def _require_empresa(empresa_id: str, token_bot_id: str = Depends(require_empresa_auth)) -> dict:
    if token_bot_id != empresa_id:
        raise HTTPException(status_code=403, detail="No autorizado para esta empresa")
    config = load_config()
    bot = next((b for b in config.get("bots", []) if b["id"] == empresa_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return bot


def _get_empresa_connections(empresa_id: str) -> list[str]:
    """Retorna todos los bot_ids (conexiones) de esta empresa."""
    config = load_config()
    for bot in config.get("bots", []):
        if bot["id"] != empresa_id:
            continue
        conns = []
        for phone in bot.get("phones", []):
            conns.append(phone["number"])
        for tg in bot.get("telegram", []):
            token_id = tg["token"].split(":")[0]
            conns.append(f"{empresa_id}-tg-{token_id}")
        return conns
    return []


def _get_empresa_name(empresa_id: str) -> str:
    config = load_config()
    for bot in config.get("bots", []):
        if bot["id"] == empresa_id:
            return bot.get("name", empresa_id)
    return empresa_id


# ─── Schemas ─────────────────────────────────────────────────────

class ToolIn(BaseModel):
    nombre: str
    tipo: str = "fixed_message"
    config: dict
    conexiones: list[str] = []
    contactos_incluidos: list[int] = []
    contactos_excluidos: list[int] = []
    incluir_desconocidos: bool = False
    exclusiva: bool = False

class ToolUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    config: Optional[dict] = None
    conexiones: Optional[list[str]] = None
    contactos_incluidos: Optional[list[int]] = None
    contactos_excluidos: Optional[list[int]] = None
    incluir_desconocidos: Optional[bool] = None
    exclusiva: Optional[bool] = None

class ValidateExclusivityIn(BaseModel):
    empresa_id: str
    tool_id: Optional[int] = None
    conexiones: list[str] = []
    contactos_incluidos: list[int] = []
    incluir_desconocidos: bool = False
    exclusiva: bool = False


# ─── Endpoints ───────────────────────────────────────────────────

@router.get("/empresas/{empresa_id}/tools")
async def list_tools(empresa_id: str, _: dict = Depends(_require_empresa)):
    return await db.get_tools(empresa_id)


@router.post("/empresas/{empresa_id}/tools", status_code=201)
async def create_tool(empresa_id: str, body: ToolIn, _: dict = Depends(_require_empresa)):
    if not body.nombre.strip():
        raise HTTPException(400, "El nombre es obligatorio")
    if body.tipo not in ("fixed_message",):
        raise HTTPException(400, f"Tipo inválido: {body.tipo}")

    tool_id = await db.create_tool(
        empresa_id, body.nombre.strip(), body.tipo, body.config,
        body.incluir_desconocidos, body.exclusiva,
    )
    await db.set_tool_connections(tool_id, body.conexiones)
    await db.set_tool_contacts_included(tool_id, body.contactos_incluidos)
    await db.set_tool_contacts_excluded(tool_id, body.contactos_excluidos)
    return await db.get_tool(tool_id)


@router.get("/tools/{tool_id}")
async def get_tool(tool_id: int, token_bot_id: str = Depends(require_empresa_auth)):
    tool = await db.get_tool(tool_id)
    if not tool:
        raise HTTPException(404, "Herramienta no encontrada")
    if tool["empresa_id"] != token_bot_id:
        raise HTTPException(403, "No autorizado para esta herramienta")
    return tool


@router.put("/tools/{tool_id}")
async def update_tool(tool_id: int, body: ToolUpdate, token_bot_id: str = Depends(require_empresa_auth)):
    tool = await db.get_tool(tool_id)
    if not tool:
        raise HTTPException(404, "Herramienta no encontrada")
    if tool["empresa_id"] != token_bot_id:
        raise HTTPException(403, "No autorizado para esta herramienta")

    updates = {}
    if body.nombre is not None:
        updates["nombre"] = body.nombre.strip()
    if body.tipo is not None:
        updates["tipo"] = body.tipo
    if body.config is not None:
        updates["config"] = body.config
    if body.incluir_desconocidos is not None:
        updates["incluir_desconocidos"] = body.incluir_desconocidos
    if body.exclusiva is not None:
        updates["exclusiva"] = body.exclusiva

    if updates:
        await db.update_tool(tool_id, **updates)
    if body.conexiones is not None:
        await db.set_tool_connections(tool_id, body.conexiones)
    if body.contactos_incluidos is not None:
        await db.set_tool_contacts_included(tool_id, body.contactos_incluidos)
    if body.contactos_excluidos is not None:
        await db.set_tool_contacts_excluded(tool_id, body.contactos_excluidos)

    return await db.get_tool(tool_id)


@router.delete("/tools/{tool_id}", status_code=204)
async def delete_tool(tool_id: int, token_bot_id: str = Depends(require_empresa_auth)):
    tool = await db.get_tool(tool_id)
    if not tool:
        raise HTTPException(404, "Herramienta no encontrada")
    if tool["empresa_id"] != token_bot_id:
        raise HTTPException(403, "No autorizado para esta herramienta")
    await db.delete_tool(tool_id)


@router.post("/tools/{tool_id}/toggle")
async def toggle_tool(tool_id: int, token_bot_id: str = Depends(require_empresa_auth)):
    tool = await db.get_tool(tool_id)
    if not tool:
        raise HTTPException(404, "Herramienta no encontrada")
    if tool["empresa_id"] != token_bot_id:
        raise HTTPException(403, "No autorizado para esta herramienta")
    await db.update_tool(tool_id, activa=not tool["activa"])
    return await db.get_tool(tool_id)


@router.post("/tools/validate-exclusivity")
async def validate_exclusivity(body: ValidateExclusivityIn):
    """
    Valida si la herramienta que se está creando/editando entra en conflicto con
    herramientas exclusivas existentes (cross-empresa).
    """
    if not body.exclusiva:
        return {"valid": True}

    # Resolver bot_ids a verificar
    if body.conexiones:
        bot_ids = body.conexiones
    else:
        bot_ids = _get_empresa_connections(body.empresa_id)

    if not bot_ids:
        return {"valid": True}

    conflicts = []

    async with AsyncSessionLocal() as session:
        for bot_id in bot_ids:
            # Contactos incluidos explícitamente
            check_contact_ids: list[Optional[int]] = list(body.contactos_incluidos)
            # Agregar "desconocido" (None) si incluir_desconocidos
            if body.incluir_desconocidos:
                check_contact_ids.append(None)

            for contact_id in check_contact_ids:
                # Buscar herramientas exclusivas que cubran este (bot_id, contact_id)
                if contact_id is not None:
                    # Herramientas que tienen este contacto en incluidos
                    rows = (await session.execute(text("""
                        SELECT DISTINCT t.id, t.empresa_id, t.nombre,
                               tc_conn.bot_id IS NOT NULL AS has_conn
                        FROM tools t
                        JOIN tool_contacts_included tci ON tci.tool_id = t.id AND tci.contact_id = :cid
                        LEFT JOIN tool_connections tc_conn ON tc_conn.tool_id = t.id AND tc_conn.bot_id = :bid
                        WHERE t.exclusiva = 1 AND t.activa = 1
                          AND (:tool_id IS NULL OR t.id != :tool_id)
                          AND (
                              tc_conn.bot_id IS NOT NULL
                              OR NOT EXISTS (SELECT 1 FROM tool_connections WHERE tool_id = t.id)
                          )
                    """), {"cid": contact_id, "bid": bot_id, "tool_id": body.tool_id})).fetchall()

                    for r in rows:
                        contact_row = (await session.execute(
                            text("SELECT name FROM contacts WHERE id=:id"), {"id": contact_id}
                        )).fetchone()
                        conflicts.append({
                            "bot_id": bot_id,
                            "contact_id": contact_id,
                            "contact_name": contact_row[0] if contact_row else None,
                            "conflicting_tool_id": r[0],
                            "conflicting_tool_nombre": r[2],
                            "conflicting_empresa_id": r[1],
                            "conflicting_empresa_nombre": _get_empresa_name(r[1]),
                        })
                else:
                    # Conflicto por desconocidos: herramientas con incluir_desconocidos=1
                    rows = (await session.execute(text("""
                        SELECT DISTINCT t.id, t.empresa_id, t.nombre
                        FROM tools t
                        LEFT JOIN tool_connections tc_conn ON tc_conn.tool_id = t.id AND tc_conn.bot_id = :bid
                        WHERE t.exclusiva = 1 AND t.activa = 1
                          AND t.incluir_desconocidos = 1
                          AND (:tool_id IS NULL OR t.id != :tool_id)
                          AND (
                              tc_conn.bot_id IS NOT NULL
                              OR NOT EXISTS (SELECT 1 FROM tool_connections WHERE tool_id = t.id)
                          )
                    """), {"bid": bot_id, "tool_id": body.tool_id})).fetchall()

                    for r in rows:
                        conflicts.append({
                            "bot_id": bot_id,
                            "contact_id": None,
                            "contact_name": None,
                            "conflicting_tool_id": r[0],
                            "conflicting_tool_nombre": r[2],
                            "conflicting_empresa_id": r[1],
                            "conflicting_empresa_nombre": _get_empresa_name(r[1]),
                        })

    if conflicts:
        return {"valid": False, "conflicts": conflicts}
    return {"valid": True}
