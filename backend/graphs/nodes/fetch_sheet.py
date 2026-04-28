"""
FetchSheetNode — lee una Google Sheet pública y vuelca el contenido en state.

Config:
  sheet_id:      str   — ID de Google Sheet (extraído de la URL share)
  range:         str   — Rango opcional, ej: "A1:D50" (vacío = toda la hoja)
  output:        str   — "context" (default) | "vars.sheet_data"
  format:        str   — "markdown_table" (default) | "json" | "plain_text"
  cache_minutes: float — 0 = sin caché, default 5
"""
import csv
import io
import json
import logging
import time
import httpx
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)

# cache global: sheet_cache[cache_key] = (content, timestamp)
_sheet_cache: dict[str, tuple[str, float]] = {}


def _build_url(sheet_id: str, range_param: str) -> str:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    if range_param:
        url += f"&range={range_param}"
    return url


def _csv_to_format(csv_text: str, fmt: str) -> str:
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        return ""

    if fmt == "json":
        return json.dumps(rows, ensure_ascii=False)

    if fmt == "plain_text":
        lines = []
        for row in rows:
            lines.append(" | ".join(str(v) for v in row.values()))
        return "\n".join(lines)

    # markdown_table (default)
    headers = list(rows[0].keys())
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join("---" for _ in headers) + " |"
    data_lines = [
        "| " + " | ".join(str(row.get(h, "")) for h in headers) + " |"
        for row in rows
    ]
    return "\n".join([header_line, sep_line] + data_lines)


class FetchSheetNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        sheet_id      = self.config.get("sheet_id", "").strip()
        range_param   = self.config.get("range", "").strip()
        output        = self.config.get("output", "context")
        fmt           = self.config.get("format", "markdown_table")
        cache_minutes = float(self.config.get("cache_minutes", 5))

        if not sheet_id:
            logger.warning("[FetchSheetNode] sheet_id no configurado")
            return state

        cache_key = f"{sheet_id}|{range_param}"
        now = time.monotonic()

        if cache_minutes > 0 and cache_key in _sheet_cache:
            cached_content, cached_at = _sheet_cache[cache_key]
            if now - cached_at < cache_minutes * 60:
                logger.info("[FetchSheetNode] Cache hit para %s", cache_key)
                content = cached_content
            else:
                content = await self._download(sheet_id, range_param, fmt, cache_key, now)
        else:
            content = await self._download(sheet_id, range_param, fmt, cache_key if cache_minutes > 0 else None, now)

        if content is None:
            return state

        if output == "context":
            state.context = content
        else:
            state.vars["sheet_data"] = content

        logger.info("[FetchSheetNode] %d chars → %s", len(content), output)
        return state

    async def _download(self, sheet_id: str, range_param: str, fmt: str, cache_key: str | None, now: float) -> str | None:
        url = _build_url(sheet_id, range_param)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = _csv_to_format(resp.text, fmt)
                if cache_key:
                    _sheet_cache[cache_key] = (content, now)
                logger.info("[FetchSheetNode] Descargado %s: %d chars", url[:80], len(content))
                return content
        except Exception as e:
            logger.error("[FetchSheetNode] Error descargando %s: %s", url[:80], e)
            return None

    @classmethod
    def config_schema(cls) -> dict:
        return {
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
            "output": {
                "type":    "select",
                "label":   "Destino",
                "default": "context",
                "options": [
                    {"value": "context",         "label": "state.context"},
                    {"value": "vars.sheet_data", "label": "state.vars.sheet_data"},
                ],
            },
            "format": {
                "type":    "select",
                "label":   "Formato",
                "default": "markdown_table",
                "options": [
                    {"value": "markdown_table", "label": "Tabla Markdown"},
                    {"value": "json",           "label": "JSON"},
                    {"value": "plain_text",     "label": "Texto plano"},
                ],
            },
            "cache_minutes": {
                "type":    "float",
                "label":   "Caché (minutos)",
                "default": 5,
                "hint":    "0 = sin caché, siempre descarga",
            },
        }
