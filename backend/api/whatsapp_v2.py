"""
WhatsApp v2 API — gestión de instancias OpenWA y recepción de webhooks.

Endpoints:
  POST /api/wa-v2/inbound          → webhook de OpenWA (sin auth, solo localhost)
  GET  /api/wa-v2/status           → lista instancias + estado
  GET  /api/wa-v2/qr/{phone}       → QR actual de una instancia (polling)
  POST /api/wa-v2/start/{phone}    → inicia instancia OpenWA
  POST /api/wa-v2/stop/{phone}     → detiene instancia
  POST /api/wa-v2/send             → envía mensaje (testing/flows)
  POST /api/wa-v2/sync/{phone}     → importa historial completo de un contacto
"""
import logging
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

from api.deps import require_admin
from automation.whatsapp_v2 import wa_v2_manager, _BASE_PORT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wa-v2", tags=["whatsapp-v2"])


# ── Webhook (sin auth — solo localhost) ──────────────────────────────────────

@router.post("/inbound")
async def inbound_webhook(request: Request):
    payload = await request.json()
    logger.debug("[wa-v2] inbound event=%r", payload.get("event") or payload.get("type", "?"))
    await wa_v2_manager.handle_webhook(payload)
    return {"ok": True}


# ── Estado ───────────────────────────────────────────────────────────────────

@router.get("/status", dependencies=[Depends(require_admin)])
async def status():
    return {"instances": wa_v2_manager.status()}


@router.get("/qr/{phone}", dependencies=[Depends(require_admin)])
async def get_qr(phone: str):
    """Polling del QR de una instancia. Devuelve {status, qr?}."""
    return wa_v2_manager.get_qr(phone)


# ── Gestión de instancias (admin) ────────────────────────────────────────────

class StartBody(BaseModel):
    port: int | None = None
    webhook_url: str | None = None


@router.post("/start/{phone}", dependencies=[Depends(require_admin)])
async def start_instance(phone: str, body: StartBody = StartBody()):
    v2_count = len([i for i in wa_v2_manager.status()])
    port = body.port or (_BASE_PORT + v2_count)
    backend_port = os.getenv("BACKEND_PORT", "8003")
    webhook_url = body.webhook_url or f"http://localhost:{backend_port}/api/wa-v2/inbound"
    try:
        await wa_v2_manager.start_instance(phone, port, webhook_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"started": phone, "port": port}


@router.post("/stop/{phone}", dependencies=[Depends(require_admin)])
async def stop_instance(phone: str):
    await wa_v2_manager.stop_instance(phone)
    return {"stopped": phone}


# ── Envío de mensajes ────────────────────────────────────────────────────────

class SendBody(BaseModel):
    phone: str
    to: str
    text: str


@router.post("/send", dependencies=[Depends(require_admin)])
async def send_message(body: SendBody):
    try:
        result = await wa_v2_manager.send_message(body.phone, body.to, body.text)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


# ── Sync de historial ────────────────────────────────────────────────────────

class SyncBody(BaseModel):
    contact: str   # número del contacto (sin @c.us)


@router.post("/sync/{phone}", dependencies=[Depends(require_admin)])
async def sync_history(phone: str, body: SyncBody):
    """
    Importa el historial completo del chat {phone} ↔ {contact} desde OpenWA
    y lo procesa por run_flows(from_delta_sync=True).

    Equivalente al _run_delta_sync de v1 pero sin scraping DOM — una sola llamada REST.
    """
    contact_jid = f"{body.contact}@c.us"
    try:
        msgs = await wa_v2_manager.get_history(phone, contact_jid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    from graphs.compiler import run_flows
    from graphs.nodes.state import FlowState

    # Ordenar cronológico (más antiguo primero) para que el sumarizador acumule en orden
    msgs_sorted = sorted(msgs, key=lambda m: m.get("t", 0))

    processed = 0
    for msg in msgs_sorted:
        if msg.get("fromMe"):
            continue
        body_text = msg.get("body", "")
        if not body_text or not body_text.strip():
            continue
        ts = msg.get("t")
        timestamp = datetime.fromtimestamp(ts) if ts else None
        sender = msg.get("sender") or {}
        contact_name = sender.get("pushname", "")

        state = FlowState(
            canal="whatsapp_v2",
            message=body_text,
            message_type="text",
            contact_phone=body.contact,
            contact_name=contact_name,
            connection_id=phone,
            from_delta_sync=True,
            timestamp=timestamp,
        )
        await run_flows(state, connection_id=phone)
        processed += 1

    logger.info("[wa-v2] sync %s ↔ %s: %d mensajes procesados", phone, body.contact, processed)
    return {"ok": True, "processed": processed, "total": len(msgs)}
