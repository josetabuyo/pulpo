import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
CLIENT_PASSWORD = os.getenv("CLIENT_PASSWORD", "conectar")


class AuthBody(BaseModel):
    password: str


@router.post("/auth")
def auth(body: AuthBody):
    if body.password == ADMIN_PASSWORD:
        return {"ok": True, "role": "admin"}
    if body.password == CLIENT_PASSWORD:
        return {"ok": True, "role": "client"}
    raise HTTPException(status_code=401, detail={"ok": False, "error": "Contraseña incorrecta"})
