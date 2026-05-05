"""
SearchSheetNode — busca en una Google Sheet pública el ítem que coincide con el mensaje.

Reemplaza VectorSearchNode modo "inline" cuando los datos viven en una hoja
que el cliente edita directamente, en lugar de estar hardcodeados en el flow.

Config:
  sheet_id:      str   — ID de Google Sheet
  range:         str   — Rango opcional
  search_field:  str   — Columna por la que buscar (default: "oficio")
  cache_minutes: float — default 5

Salida (igual que VectorSearchNode inline):
  Match → state.vars con todas las columnas del ítem, state.context con JSON del ítem
  Sin match → state.vars[search_field] = valor buscado, state.context = JSON de filas activas
"""
import csv
import io
import json
import logging
import time
import httpx
from .base import BaseNode
from .state import FlowState
from .vector_search import _normalize, _match, _identify_field_value

logger = logging.getLogger(__name__)

_rows_cache: dict[str, tuple[list[dict], float]] = {}


def _build_url(sheet_id: str, range_param: str) -> str:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    if range_param:
        url += f"&range={range_param}"
    return url


def _is_active(row: dict) -> bool:
    val = str(row.get("activo", "true")).strip().lower()
    return val in {"true", "1", "sí", "si", ""}


async def _fetch_rows(sheet_id: str, range_param: str, cache_minutes: float) -> list[dict] | None:
    cache_key = f"{sheet_id}|{range_param}"
    now = time.monotonic()

    if cache_minutes > 0 and cache_key in _rows_cache:
        cached_rows, cached_at = _rows_cache[cache_key]
        if now - cached_at < cache_minutes * 60:
            logger.info("[SearchSheetNode] Cache hit para %s", cache_key)
            return cached_rows

    url = _build_url(sheet_id, range_param)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            reader = csv.DictReader(io.StringIO(resp.text))
            rows = list(reader)
            if cache_minutes > 0:
                _rows_cache[cache_key] = (rows, now)
            logger.info("[SearchSheetNode] Descargado %s: %d filas", url[:80], len(rows))
            return rows
    except Exception as e:
        logger.error("[SearchSheetNode] Error descargando %s: %s", url[:80], e)
        return None


class SearchSheetNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        sheet_id      = self.config.get("sheet_id", "").strip()
        range_param   = self.config.get("range", "").strip()
        search_field  = self.config.get("search_field", "oficio")
        cache_minutes = float(self.config.get("cache_minutes", 5))

        if not sheet_id:
            logger.warning("[SearchSheetNode] sheet_id no configurado")
            return state

        rows = await _fetch_rows(sheet_id, range_param, cache_minutes)
        if rows is None:
            return state

        # Valores posibles del campo de búsqueda para orientar al LLM
        possible_values = list({
            row.get(search_field, "").lower()
            for row in rows
            if row.get(search_field)
        })

        search_value = await _identify_field_value(state.message, search_field, possible_values)

        # Filas activas que coinciden
        matches = [
            row for row in rows
            if _is_active(row) and _match(search_value, str(row.get(search_field, "")))
        ]

        if not matches:
            logger.info("[SearchSheetNode] Sin match para %s='%s'", search_field, search_value)
            state.vars[search_field] = search_value
            disponibles = [row for row in rows if _is_active(row)]
            if disponibles:
                state.context = json.dumps(disponibles, ensure_ascii=False)
            return state

        item = matches[0]
        logger.info("[SearchSheetNode] Match: %s='%s' → %s", search_field, search_value, item)

        for key, value in item.items():
            if key != "activo":
                state.vars[key] = value
        state.vars[search_field] = search_value
        state.context = json.dumps(item, ensure_ascii=False)

        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "google_account": {
                "type":    "google_account_select",
                "label":   "Cuenta Google",
                "default": "default",
            },
            "sheet_id": {
                "type":    "string",
                "label":   "ID de Google Sheet",
                "default": "",
                "hint":    "El ID de la URL: docs.google.com/spreadsheets/d/<ID>/...",
                "required": True,
            },
            "range": {
                "type":    "string",
                "label":   "Rango (opcional)",
                "default": "",
                "hint":    "Ej: A1:D50 — vacío = toda la hoja",
            },
            "search_field": {
                "type":    "string",
                "label":   "Campo de búsqueda",
                "default": "oficio",
                "hint":    "Columna de la hoja por la que se busca (ej: oficio, categoria)",
            },
            "cache_minutes": {
                "type":    "float",
                "label":   "Caché (minutos)",
                "default": 5,
                "hint":    "0 = sin caché, siempre descarga",
            },
        }
