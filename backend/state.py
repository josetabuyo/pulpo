"""
Registro en memoria de sesiones activas.
Equivalente al objeto `clients` de Node.js.

Estructura de cada entrada:
  clients[session_id] = {
      "status":  str,   # stopped | connecting | ready | disconnected | failed
      "qr":      str | None,
      "connection_id": str,
      "type":    "telegram",
      "client":  objeto runtime | None,
  }
"""

from typing import Any

clients: dict[str, dict[str, Any]] = {}
