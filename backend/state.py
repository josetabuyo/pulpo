"""
Registro en memoria de sesiones activas.
Equivalente al objeto `clients` de Node.js.

Estructura de cada entrada:
  clients[session_id] = {
      "status":  str,   # stopped | connecting | qr_ready | authenticated | ready | disconnected | failed
      "qr":      str | None,
      "bot_id":  str,
      "type":    "whatsapp" | "telegram",
      "client":  objeto runtime | None,
  }
"""

from typing import Any

clients: dict[str, dict[str, Any]] = {}
