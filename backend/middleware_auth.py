from fastapi import HTTPException, Request
from auth_jwt import decode_access_token


def get_empresa_id_from_token(request: Request) -> str | None:
    """Extrae empresa_id del Bearer token si es válido, o None."""
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    return decode_access_token(token)


async def require_empresa_auth(request: Request) -> str:
    """Dependency FastAPI: extrae y valida Bearer token. Retorna empresa_id."""
    empresa_id = get_empresa_id_from_token(request)
    if not empresa_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    return empresa_id
