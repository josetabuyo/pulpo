"""
FetchNode — obtiene contenido externo y lo guarda en state.data["context"].

Config:
  source:        str — "facebook" | "http"
  bot_id:        str — bot para credenciales de Facebook (si vacío, usa state.bot_id)
  url:           str — URL para HTTP GET (solo si source="http").
                       Soporta templates: {message} y {query} se sustituyen con el
                       input del usuario antes de hacer el request.
                       Ej: https://api.ejemplo.com/buscar?q={message}
  extract:       str — "text" | "json" | "html" (para source="http")
"""
import asyncio
import logging

from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)

# Claves con semántica propia del engine — no deben ser pisadas por datos externos
_RESERVED_KEYS = frozenset({"route", "reply", "context", "query", "fb_posts", "source_urls", "_node_errors"})


class FetchNode(BaseNode):
    label = "Fetch externo"
    color = "#1e40af"
    description = "Obtiene datos externos: posts de Facebook, imagen de post, o HTTP genérico."

    async def run(self, state: FlowState) -> FlowState:
        source = self.config.get("source", "facebook")

        if source == "facebook":
            await self._fetch_facebook(state)
        elif source == "http":
            await self._fetch_http(state)
        else:
            logger.warning("[FetchNode] source desconocido: %s", source)

        return state

    async def _fetch_facebook(self, state: FlowState) -> None:
        # page_id: config explícito tiene precedencia, luego bot_id del state
        page_id    = self.config.get("fb_page_id") or state.bot_id
        numeric_id = self.config.get("fb_numeric_id", "")

        # Queries: usa state.data["query"] (multi-línea) o el mensaje directo
        if state.data.get("query"):
            queries = [q.strip() for q in state.data["query"].splitlines() if q.strip()]
        else:
            queries = [state.message]

        try:
            # Import lazy: fetch_facebook arrastra Playwright — solo si se usa
            from pulpo.nodes import fetch_facebook

            results = await asyncio.gather(*[
                fetch_facebook.fetch_posts(page_id, q, numeric_id) for q in queries
            ])

            # Deduplicar por texto
            seen: set[str] = set()
            fb_posts: list[dict] = []
            for posts in results:
                for post in posts:
                    key = post["text"][:100]
                    if key not in seen:
                        seen.add(key)
                        fb_posts.append(post)

            state.data["fb_posts"] = fb_posts

            # Formatear contexto con URL de cada post para que el LLM pueda citar la fuente
            parts = []
            for i, p in enumerate(fb_posts):
                if not p["text"]:
                    continue
                header = f"[Post {i}]"
                if p.get("url"):
                    header += f"\nURL: {p['url']}"
                parts.append(f"{header}\n{p['text']}")
            context = "\n\n".join(parts)
            state.data["context"] = context
            logger.info("[FetchNode] Facebook: %d posts, %d chars", len(fb_posts), len(context))

            # Guardar URLs para appendar al reply
            seen_urls: set[str] = set()
            source_urls: list[str] = []
            for p in fb_posts:
                for u in (p.get("post_urls") or [p.get("url")] if p.get("url") else []):
                    if u and u not in seen_urls:
                        seen_urls.add(u)
                        source_urls.append(u)
            if source_urls:
                # BUG: solo el primer link tiene sentido — ver BUG_LUGANENSE_LINKS.md
                state.data["source_urls"] = source_urls[:1]

        except Exception as e:
            logger.error("[FetchNode] Error fetching Facebook: %s", e)

    async def _fetch_http(self, state: FlowState) -> None:
        url                      = self.config.get("url", "")
        extract                  = self.config.get("extract", "text")
        extract_first_to_vars    = self.config.get("extract_first_result_to_vars", False)
        if not url:
            logger.warning("[FetchNode] http sin url configurada")
            return
        # Template substitution: {message} and {query} are replaced with user input
        url = url.replace("{message}", state.message or "")
        url = url.replace("{query}", state.data.get("query") or state.message or "")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                if extract == "json":
                    state.data["context"] = resp.text
                elif extract == "html":
                    state.data["context"] = resp.text
                else:
                    # extraer texto plano básico
                    import re
                    text = re.sub(r"<[^>]+>", " ", resp.text)
                    text = re.sub(r"\s+", " ", text).strip()
                    state.data["context"] = text[:5000]
            logger.info("[FetchNode] http %s: %d chars", url[:60], len(state.data.get("context", "")))

            # Extrae el primer resultado de {"results": [...]} a state.vars
            if extract_first_to_vars and extract == "json" and state.data.get("context"):
                import json as _json
                try:
                    data = _json.loads(state.data["context"])
                    results = data.get("results") if isinstance(data, dict) else None
                    if results and isinstance(results, list) and results[0]:
                        for k, v in results[0].items():
                            if k in _RESERVED_KEYS:
                                logger.warning("[FetchNode] campo externo '%s' colisiona con clave reservada — ignorado", k)
                                continue
                            state.data[k] = v
                        # Expandir contactos: [{tipo, valor}] a vars planos por tipo
                        contactos = results[0].get("contactos")
                        if isinstance(contactos, list):
                            for c in contactos:
                                tipo = c.get("tipo") if isinstance(c, dict) else None
                                valor = c.get("valor") if isinstance(c, dict) else None
                                if tipo and valor and tipo not in _RESERVED_KEYS:
                                    state.data[tipo] = valor
                        logger.info("[FetchNode] extract_first_to_vars: %d campos → vars", len(results[0]))
                except Exception as ex:
                    logger.warning("[FetchNode] extract_first_to_vars falló: %s", ex)
        except Exception as e:
            logger.error("[FetchNode] Error HTTP GET %s: %s", url, e)

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "source": {
                "type":    "select",
                "label":   "Qué hace este nodo",
                "default": "facebook",
                "options": [
                    {"value": "facebook", "label": "Scrapear posts de Facebook"},
                    {"value": "http",     "label": "Fetch HTTP externo"},
                ],
            },
            "fb_page_id": {
                "type":    "string",
                "label":   "Página de Facebook (slug)",
                "default": "",
                "hint":    "ej: luganense, cnn, tuportal",
                "show_if": {"source": "facebook"},
            },
            "fb_numeric_id": {
                "type":    "string",
                "label":   "ID numérico FB (opcional)",
                "default": "",
                "hint":    "Habilita búsqueda directa. Ej: 100070998865103",
                "show_if": {"source": "facebook"},
            },
            "url": {
                "type":    "string",
                "label":   "URL",
                "default": "",
                "hint":    "https://api.ejemplo.com/buscar?q={message} — {message} y {query} se reemplazan con el input del usuario",
                "show_if": {"source": "http"},
            },
            "extract": {
                "type":    "select",
                "label":   "Formato de respuesta",
                "default": "text",
                "options": ["text", "json", "html"],
                "show_if": {"source": "http"},
            },
        }
