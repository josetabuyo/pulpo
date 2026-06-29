from fastapi import HTTPException, Request
from pulpo.core.auth_jwt import decode_access_token


def get_bot_id_from_token(request: Request) -> str | None:
    """Extrae bot_id del Bearer token si es válido, o None."""
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    return decode_access_token(token)


async def require_bot_auth(request: Request) -> str:
    """Dependency FastAPI: extrae y valida Bearer token. Retorna bot_id."""
    bot_id = get_bot_id_from_token(request)
    if not bot_id:
        raise HTTPException(status_code=401, detail="Token requerido o inválido")
    return bot_id
