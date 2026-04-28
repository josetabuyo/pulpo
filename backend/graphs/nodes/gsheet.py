"""
GSheetNode — conecta con una Google Sheet pública.

Modos:
  search  → filtra filas por valor exacto en una columna.
            El valor buscado lo prepara el nodo anterior (state.vars, state.query, etc.)
            Sin LLM interno.
  append  → agrega una fila nueva a la hoja.
            Requiere service account (GOOGLE_SERVICE_ACCOUNT_JSON en .env).

Para search: la hoja debe ser pública ("cualquiera con el enlace puede ver").
Para append: la hoja debe estar compartida con el email del service account con permiso de editor.
"""
import csv
import io
import json
import logging
import os
import time
import httpx
from .base import BaseNode, interpolate
from .state import FlowState

logger = logging.getLogger(__name__)

_rows_cache: dict[str, tuple[list[dict], float]] = {}


def _sheet_csv_url(sheet_id: str, range_param: str) -> str:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    if range_param:
        url += f"&range={range_param}"
    return url


def _is_active(row: dict) -> bool:
    val = str(row.get("activo", "true")).strip().lower()
    return val not in {"false", "0", "no"}


async def _fetch_rows(sheet_id: str, range_param: str, cache_minutes: float) -> list[dict] | None:
    cache_key = f"{sheet_id}|{range_param}"
    now = time.monotonic()
    if cache_minutes > 0 and cache_key in _rows_cache:
        rows, ts = _rows_cache[cache_key]
        if now - ts < cache_minutes * 60:
            logger.info("[GSheetNode] Cache hit %s", cache_key)
            return rows
    url = _sheet_csv_url(sheet_id, range_param)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            rows = list(csv.DictReader(io.StringIO(resp.text)))
            if cache_minutes > 0:
                _rows_cache[cache_key] = (rows, now)
            logger.info("[GSheetNode] Descargado %s: %d filas", url[:80], len(rows))
            return rows
    except Exception as e:
        logger.error("[GSheetNode] Error descargando %s: %s", url[:80], e)
        return None


def _get_search_value(state: FlowState, source: str) -> str:
    """
    Lee el valor de búsqueda del campo configurado del state.
    source puede ser: "query", "message", "vars.oficio", "vars.categoria", etc.
    """
    if source == "query":
        return (state.query or "").strip()
    if source == "message":
        return (state.message or "").strip()
    if source.startswith("vars."):
        key = source[5:]
        return str(state.vars.get(key, "")).strip()
    return ""


class GSheetNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        mode = self.config.get("mode", "search")
        if mode == "search":
            return await self._search(state)
        if mode == "read_all":
            return await self._read_all(state)
        if mode == "append":
            return await self._append(state)
        logger.warning("[GSheetNode] Modo desconocido: %s", mode)
        return state

    # ── Search ────────────────────────────────────────────────────────────────

    async def _search(self, state: FlowState) -> FlowState:
        sheet_id      = self.config.get("sheet_id", "").strip()
        range_param   = self.config.get("range", "").strip()
        search_col    = self.config.get("search_column", "").strip()
        query_source  = self.config.get("query_source", "query")
        exact_match   = self.config.get("exact_match", True)
        cache_minutes = float(self.config.get("cache_minutes", 5))

        if not sheet_id or not search_col:
            logger.warning("[GSheetNode] search: sheet_id o search_column no configurado")
            return state

        search_value = _get_search_value(state, query_source)
        if not search_value:
            logger.warning("[GSheetNode] search: valor de búsqueda vacío (source='%s')", query_source)
            return state

        rows = await _fetch_rows(sheet_id, range_param, cache_minutes)
        if rows is None:
            return state

        sv = search_value.lower()
        if exact_match:
            matches = [r for r in rows if _is_active(r) and r.get(search_col, "").lower() == sv]
        else:
            matches = [r for r in rows if _is_active(r) and sv in r.get(search_col, "").lower()]

        if not matches:
            logger.info("[GSheetNode] Sin resultado para %s='%s'", search_col, search_value)
            state.vars[search_col] = search_value
            disponibles = [r for r in rows if _is_active(r)]
            if disponibles:
                state.context = json.dumps(disponibles, ensure_ascii=False)
            return state

        item = matches[0]
        logger.info("[GSheetNode] Match: %s='%s'", search_col, search_value)
        for key, value in item.items():
            if key != "activo":
                state.vars[key] = value
        state.context = json.dumps(item, ensure_ascii=False)
        return state

    # ── Read all ──────────────────────────────────────────────────────────────

    async def _read_all(self, state: FlowState) -> FlowState:
        sheet_id      = self.config.get("sheet_id", "").strip()
        range_param   = self.config.get("range", "").strip()
        output        = self.config.get("output", "context")
        fmt           = self.config.get("format", "json")
        cache_minutes = float(self.config.get("cache_minutes", 5))

        if not sheet_id:
            logger.warning("[GSheetNode] read_all: sheet_id no configurado")
            return state

        rows = await _fetch_rows(sheet_id, range_param, cache_minutes)
        if not rows:
            return state

        if fmt == "json":
            content = json.dumps(rows, ensure_ascii=False)
        else:
            import csv as _csv
            buf = io.StringIO()
            headers = list(rows[0].keys())
            w = _csv.DictWriter(buf, fieldnames=headers)
            w.writeheader()
            w.writerows(rows)
            content = buf.getvalue()

        if output == "context":
            state.context = content
        else:
            state.vars["sheet_data"] = content

        logger.info("[GSheetNode] read_all: %d filas → %s", len(rows), output)
        return state

    # ── Append ────────────────────────────────────────────────────────────────

    async def _append(self, state: FlowState) -> FlowState:
        sheet_id   = self.config.get("sheet_id", "").strip()
        sheet_name = self.config.get("sheet_name", "Sheet1").strip()
        columns    = self.config.get("columns", [])  # [{"header": "nombre", "source": "vars.nombre"}, ...]

        if not sheet_id:
            logger.warning("[GSheetNode] append: sheet_id no configurado")
            return state

        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not sa_json:
            logger.error("[GSheetNode] append: falta GOOGLE_SERVICE_ACCOUNT_JSON en .env")
            return state

        values = [_get_search_value(state, col.get("source", "")) for col in columns]

        try:
            import google.auth
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_info = json.loads(sa_json)
            creds = service_account.Credentials.from_service_account_info(
                creds_info,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            service = build("sheets", "v4", credentials=creds, cache_discovery=False)
            service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": [values]},
            ).execute()
            logger.info("[GSheetNode] append OK: %s", values)
        except Exception as e:
            logger.error("[GSheetNode] Error en append: %s", e)

        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "mode": {
                "type":    "select",
                "label":   "Modo",
                "default": "search",
                "options": [
                    {"value": "search",   "label": "Buscar fila"},
                    {"value": "read_all", "label": "Bajar toda la planilla"},
                    {"value": "append",   "label": "Agregar fila"},
                ],
            },
            # ── Común ──────────────────────────────────────────────────────────
            "sheet_id": {
                "type":     "string",
                "label":    "ID de Google Sheet",
                "default":  "",
                "hint":     "El ID de la URL: docs.google.com/spreadsheets/d/<ID>/...",
                "required": True,
            },
            "range": {
                "type":    "string",
                "label":   "Rango (opcional)",
                "default": "",
                "hint":    "Ej: A1:D100 — vacío = toda la hoja",
            },
            # ── Search ─────────────────────────────────────────────────────────
            "search_column": {
                "type":    "string",
                "label":   "Columna de búsqueda",
                "default": "",
                "hint":    "Nombre exacto del encabezado. Ej: oficio",
                "show_if": {"mode": "search"},
            },
            "query_source": {
                "type":    "select",
                "label":   "Origen del valor a buscar",
                "default": "query",
                "options": [
                    {"value": "query",       "label": "state.query"},
                    {"value": "message",     "label": "state.message"},
                    {"value": "vars.oficio", "label": "state.vars.oficio"},
                ],
                "hint":    "El nodo anterior debe haber puesto el valor ahí",
                "show_if": {"mode": "search"},
            },
            "exact_match": {
                "type":    "bool",
                "label":   "Coincidencia exacta",
                "default": True,
                "hint":    "Desactivar para buscar por contiene",
                "show_if": {"mode": "search"},
            },
            "cache_minutes": {
                "type":    "float",
                "label":   "Caché (minutos)",
                "default": 5,
            },
            # ── Read all ───────────────────────────────────────────────────────
            "output": {
                "type":    "select",
                "label":   "Destino",
                "default": "context",
                "options": [
                    {"value": "context",         "label": "state.context"},
                    {"value": "vars.sheet_data", "label": "state.vars.sheet_data"},
                ],
                "show_if": {"mode": "read_all"},
            },
            "format": {
                "type":    "select",
                "label":   "Formato",
                "default": "json",
                "options": [
                    {"value": "json", "label": "JSON (recomendado para LLM)"},
                    {"value": "csv",  "label": "CSV"},
                ],
                "show_if": {"mode": "read_all"},
            },
            # ── Append ─────────────────────────────────────────────────────────
            "sheet_name": {
                "type":    "string",
                "label":   "Nombre de la hoja",
                "default": "Sheet1",
                "hint":    "La pestaña donde agregar la fila",
                "show_if": {"mode": "append"},
            },
            "columns": {
                "type":    "json",
                "label":   "Columnas a escribir",
                "default": [],
                "hint":    '[{"header": "nombre", "source": "vars.nombre"}, ...]',
                "show_if": {"mode": "append"},
            },
        }
