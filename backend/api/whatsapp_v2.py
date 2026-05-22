"""
WhatsApp v2 API — gestión de instancias OpenWA y recepción de webhooks.

Endpoints:
  POST /api/wa-v2/inbound          → webhook de OpenWA (sin auth, solo localhost)
  GET  /api/wa-v2/status           → lista instancias activas
  POST /api/wa-v2/start/{phone}    → inicia instancia OpenWA
  POST /api/wa-v2/stop/{phone}     → detiene instancia
  POST /api/wa-v2/send             → envía mensaje (testing/flows)
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from automation.whatsapp_v2 import wa_v2_manager, _BASE_PORT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wa-v2", tags=["whatsapp-v2"])


# ── Webhook ──────────────────────────────────────────────────────────────────

@router.post("/inbound")
async def inbound_webhook(request: Request):
    """Recibe mensajes entrantes de OpenWA. Solo se espera llamado desde localhost."""
    payload = await request.json()
    logger.debug("[wa-v2] inbound: %s", payload.get("type", "?"))
    await wa_v2_manager.handle_webhook(payload)
    return {"ok": True}


# ── Estado ───────────────────────────────────────────────────────────────────

@router.get("/status")
async def status():
    return {"instances": wa_v2_manager.status()}


# ── Gestión de instancias ────────────────────────────────────────────────────

class StartBody(BaseModel):
    port: int | None = None
    webhook_url: str | None = None


@router.post("/start/{phone}")
async def start_instance(phone: str, body: StartBody = StartBody()):
    phones_active = wa_v2_manager.status()
    port = body.port or (_BASE_PORT + len(phones_active))
    webhook_url = body.webhook_url or f"http://localhost:8003/api/wa-v2/inbound"
    try:
        await wa_v2_manager.start_instance(phone, port, webhook_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"started": phone, "port": port}


@router.post("/stop/{phone}")
async def stop_instance(phone: str):
    await wa_v2_manager.stop_instance(phone)
    return {"stopped": phone}


# ── Envío de mensajes ────────────────────────────────────────────────────────

class SendBody(BaseModel):
    phone: str
    to: str
    text: str


@router.post("/send")
async def send_message(body: SendBody):
    try:
        result = await wa_v2_manager.send_message(body.phone, body.to, body.text)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result
