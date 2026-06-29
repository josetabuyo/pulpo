from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pulpo.interfaces.ui.deps import ADMIN_PASSWORD, CLIENT_PASSWORD

router = APIRouter()


class AuthBody(BaseModel):
    password: str


@router.post("/auth")
def auth(body: AuthBody):
    if body.password == ADMIN_PASSWORD:
        return {"ok": True, "role": "admin"}
    if body.password == CLIENT_PASSWORD:
        return {"ok": True, "role": "client"}
    raise HTTPException(status_code=401, detail={"ok": False, "error": "Contraseña incorrecta"})
