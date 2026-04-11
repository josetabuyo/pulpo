from fastapi import APIRouter, HTTPException, Depends, Request, Header
from pydantic import BaseModel

from api.deps import require_admin, ADMIN_PASSWORD
from config import load_config, save_config, get_connection_default_filter, set_connection_default_filter
from middleware_auth import get_empresa_id_from_token
from state import clients

_ADMIN_SENTINEL = "__admin__"

def _require_empresa_or_admin(request: Request, x_password: str = Header(default=None)) -> str:
    if x_password == ADMIN_PASSWORD:
        return _ADMIN_SENTINEL
    empresa_id = get_empresa_id_from_token(request)
    if not empresa_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    return empresa_id

def _check_number_access(number: str, token_empresa_id: str):
    """Verifica que el número pertenezca a la empresa autenticada (o es admin)."""
    if token_empresa_id == _ADMIN_SENTINEL:
        return
    config = load_config()
    for empresa in config.get("empresas", []):
        if empresa["id"] == token_empresa_id:
            phones = [p["number"] for p in empresa.get("phones", [])]
            if number in phones:
                return
            raise HTTPException(403, "No autorizado para este número")
    raise HTTPException(403, "Empresa no encontrada")

router = APIRouter()


@router.get("/connections", dependencies=[Depends(require_admin)])
def get_connections():
    config = load_config()
    result = []
    for empresa in config.get("empresas", []):
        for phone in empresa.get("phones", []):
            session_id = phone["number"]
            result.append({
                "empresaId": empresa["id"],
                "empresaName": empresa["name"],
                "number": phone["number"],
                "sessionId": session_id,
                "status": clients.get(session_id, {}).get("status", "stopped"),
            })
    return result


class PhoneCreate(BaseModel):
    empresaId: str
    empresaName: str | None = None
    number: str


@router.post("/connections", dependencies=[Depends(require_admin)], status_code=201)
def create_connection(body: PhoneCreate):
    if not body.empresaId or not body.number:
        raise HTTPException(status_code=400, detail="empresaId y number son requeridos")

    config = load_config()
    empresa = next((e for e in config.get("empresas", []) if e["id"] == body.empresaId), None)

    if not empresa:
        if not body.empresaName:
            raise HTTPException(status_code=400, detail="Empresa nueva requiere empresaName")
        empresa = {"id": body.empresaId, "name": body.empresaName, "phones": []}
        config.setdefault("empresas", []).append(empresa)

    for e in config.get("empresas", []):
        if any(p["number"] == body.number for p in e.get("phones", [])):
            raise HTTPException(status_code=409, detail=f'El número ya está en la empresa "{e["name"]}". Movelo desde ahí.')

    empresa.setdefault("phones", []).append({"number": body.number})

    save_config(config)
    return {"ok": True, "sessionId": body.number}



@router.delete("/connections/{number}", dependencies=[Depends(require_admin)])
def delete_connection(number: str):
    config = load_config()
    for empresa in config.get("empresas", []):
        idx = next((i for i, p in enumerate(empresa.get("phones", [])) if p["number"] == number), None)
        if idx is not None:
            session_id = number
            if session_id in clients:
                try:
                    clients[session_id]["client"].destroy()
                except Exception:
                    pass
                del clients[session_id]
            empresa["phones"].pop(idx)
            config["empresas"] = [e for e in config["empresas"] if e.get("phones")]
            save_config(config)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Número no encontrado")


class MovePhone(BaseModel):
    targetEmpresaId: str


@router.post("/connections/{number}/move", dependencies=[Depends(require_admin)])
def move_connection(number: str, body: MovePhone):
    if not body.targetEmpresaId:
        raise HTTPException(status_code=400, detail="targetEmpresaId requerido")

    config = load_config()
    target_empresa = next((e for e in config.get("empresas", []) if e["id"] == body.targetEmpresaId), None)
    if not target_empresa:
        raise HTTPException(status_code=404, detail="Empresa destino no encontrada")

    source_empresa = None
    phone_entry = None
    for e in config.get("empresas", []):
        idx = next((i for i, p in enumerate(e.get("phones", [])) if p["number"] == number), None)
        if idx is not None:
            source_empresa = e
            phone_entry = e["phones"].pop(idx)
            break

    if not source_empresa:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    if source_empresa["id"] == body.targetEmpresaId:
        raise HTTPException(status_code=400, detail="El teléfono ya está en esa empresa")

    target_empresa.setdefault("phones", []).append(phone_entry)
    save_config(config)
    return {"ok": True, "from": source_empresa["id"], "to": body.targetEmpresaId}


# ─── Filtro default por conexión ─────────────────────────────────────────────

class DefaultFilterBody(BaseModel):
    include_all_known: bool = False
    include_unknown: bool = False
    included: list[str] = []
    excluded: list[str] = []


@router.get("/connections/{number}/filter-config")
def get_connection_filter(number: str, token: str = Depends(_require_empresa_or_admin)):
    """Retorna el filtro default de una conexión (o vacío si no tiene)."""
    _check_number_access(number, token)
    df = get_connection_default_filter(number)
    if df is None:
        return {"include_all_known": False, "include_unknown": False, "included": [], "excluded": []}
    return df


@router.put("/connections/{number}/filter-config")
def put_connection_filter(number: str, body: DefaultFilterBody, token: str = Depends(_require_empresa_or_admin)):
    """Guarda el filtro default de una conexión."""
    _check_number_access(number, token)
    filter_dict = body.model_dump()
    ok = set_connection_default_filter(number, filter_dict)
    if not ok:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    return {"ok": True, "filter": filter_dict}


@router.delete("/connections/{number}/filter-config", dependencies=[Depends(require_admin)])
def delete_connection_filter(number: str):
    """Elimina el filtro default de una conexión (solo admin)."""
    ok = set_connection_default_filter(number, None)
    if not ok:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    return {"ok": True}
