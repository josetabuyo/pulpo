"""Dependencias de autenticación reutilizables."""
import os
from fastapi import Header, HTTPException

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
CLIENT_PASSWORD = os.getenv("CLIENT_PASSWORD", "conectar")


def require_admin(x_password: str = Header(...)):
    if x_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="No autorizado")


def require_client(x_password: str = Header(...)):
    if x_password not in (ADMIN_PASSWORD, CLIENT_PASSWORD):
        raise HTTPException(status_code=401, detail="No autorizado")
