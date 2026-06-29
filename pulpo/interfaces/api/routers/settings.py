"""
Router: /settings

Thin FastAPI wrapper over the business layer. No auth — auth is applied
by interfaces/ui/app.py at mount time.

Route layout (parent mounts at /settings):
  GET /config/settings
  PUT /config/settings
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pulpo.business import settings as settings_svc

router = APIRouter()


@router.get("/config/settings")
def read_settings():
    try:
        return settings_svc.get_settings()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SettingsPatch(BaseModel):
    wa_poll_interval_seconds: int | None = None


@router.put("/config/settings")
def write_settings(body: SettingsPatch):
    patch = {}
    if body.wa_poll_interval_seconds is not None:
        v = max(60, min(3600, int(body.wa_poll_interval_seconds)))
        patch["wa_poll_interval_seconds"] = v
    try:
        return settings_svc.update_settings(patch=patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
