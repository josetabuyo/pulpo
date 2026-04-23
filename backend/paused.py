"""
Registro en memoria de empresas con bot pausado.

Una empresa pausada sigue conectada (WA/TG vivo) pero no genera replies.
El estado se persiste en data/paused_bots.json para sobrevivir reinicios.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_FILE = Path("data/paused_bots.json")
_paused: set[str] = set()


def _load() -> None:
    global _paused
    try:
        if _FILE.exists():
            data = json.loads(_FILE.read_text())
            _paused = set(data.get("paused", []))
            if _paused:
                logger.info("[paused] Cargadas %d empresas pausadas: %s", len(_paused), _paused)
    except Exception as e:
        logger.error("[paused] Error al cargar %s: %s", _FILE, e)


def _save() -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps({"paused": sorted(_paused)}, indent=2))
    except Exception as e:
        logger.error("[paused] Error al guardar %s: %s", _FILE, e)


def is_paused(empresa_id: str) -> bool:
    return empresa_id in _paused


def pause(empresa_id: str) -> None:
    _paused.add(empresa_id)
    _save()
    logger.warning("[paused] Bot pausado: %s", empresa_id)


def resume(empresa_id: str) -> None:
    _paused.discard(empresa_id)
    _save()
    logger.info("[paused] Bot reanudado: %s", empresa_id)


def all_paused() -> list[str]:
    return sorted(_paused)


# Cargar al importar
_load()
