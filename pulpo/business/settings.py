"""
Business logic for application settings.
No FastAPI, no HTTPException, no Pydantic — plain Python types only.
"""

from pulpo.core.config import get_settings, update_settings


def read_settings() -> dict:
    """Returns current settings dict."""
    s = get_settings()
    return {"wa_poll_interval_seconds": int(s.get("wa_poll_interval_seconds", 300))}


def write_settings(wa_poll_interval_seconds: int | None) -> dict:
    """
    Updates settings with the provided values and returns the updated settings dict.
    wa_poll_interval_seconds is clamped to [60, 3600].
    """
    patch = {}
    if wa_poll_interval_seconds is not None:
        v = max(60, min(3600, int(wa_poll_interval_seconds)))
        patch["wa_poll_interval_seconds"] = v
    s = update_settings(patch)
    return {"wa_poll_interval_seconds": int(s.get("wa_poll_interval_seconds", 300))}
