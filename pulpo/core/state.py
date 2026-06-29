from typing import Any

clients: dict[str, dict[str, Any]] = {}

# Wavi session statuses — updated by wavi_poller and interfaces/api/routers/wavi.py
# Maps session_name → 'stopped' | 'connecting' | 'ready' | 'disconnected'
wavi_status: dict[str, str] = {}
