from fastapi import APIRouter, Depends
from pydantic import BaseModel
from api.deps import require_admin
from config import get_settings, update_settings

router = APIRouter()


@router.get("/config/settings", dependencies=[Depends(require_admin)])
def read_settings():
    s = get_settings()
    return {"wa_poll_interval_seconds": int(s.get("wa_poll_interval_seconds", 300))}


class SettingsPatch(BaseModel):
    wa_poll_interval_seconds: int | None = None


@router.put("/config/settings", dependencies=[Depends(require_admin)])
def write_settings(body: SettingsPatch):
    patch = {}
    if body.wa_poll_interval_seconds is not None:
        v = max(60, min(3600, int(body.wa_poll_interval_seconds)))
        patch["wa_poll_interval_seconds"] = v
    s = update_settings(patch)
    return {"wa_poll_interval_seconds": int(s.get("wa_poll_interval_seconds", 300))}
