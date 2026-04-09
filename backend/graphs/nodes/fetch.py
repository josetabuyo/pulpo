"""
FetchNode — obtiene contenido externo y lo guarda en state.context.

Config:
  source:     str — "facebook" | "fb_image" | "http"
  empresa_id: str — empresa para credenciales de Facebook (si vacío, usa state.empresa_id)
  url:        str — URL para HTTP GET (solo si source="http")
  extract:    str — "text" | "json" | "html" (para source="http")
"""
import logging
from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


class FetchNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        source = self.config.get("source", "facebook")

        if source == "facebook":
            await self._fetch_facebook(state)
        elif source == "fb_image":
            self._extract_fb_image(state)
        elif source == "http":
            await self._fetch_http(state)
        else:
            logger.warning("[FetchNode] source desconocido: %s", source)

        return state

    async def _fetch_facebook(self, state: FlowState) -> None:
        # page_id: config explícito tiene precedencia, luego empresa_id del state
        page_id    = self.config.get("fb_page_id") or state.empresa_id
        numeric_id = self.config.get("fb_numeric_id", "")

        # Queries: usa state.query (multi-línea) o el mensaje directo
        if state.query:
            queries = [q.strip() for q in state.query.splitlines() if q.strip()]
        else:
            queries = [state.message]

        try:
            import asyncio
            from nodes import fetch_facebook

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

            state.fb_posts = fb_posts

            # Formatear contexto con URL de cada post para que el LLM pueda citar la fuente
            parts = []
            for i, p in enumerate(fb_posts):
                if not p["text"]:
                    continue
                header = f"[Post {i}]"
                if p.get("url"):
                    header += f"\nURL: {p['url']}"
                parts.append(f"{header}\n{p['text']}")
            state.context = "\n\n".join(parts)
            logger.info("[FetchNode] Facebook: %d posts, %d chars", len(fb_posts), len(state.context))

        except Exception as e:
            logger.error("[FetchNode] Error fetching Facebook: %s", e)

    def _extract_fb_image(self, state: FlowState) -> None:
        """Extrae la imagen del post relevante ya cargado en state.fb_posts."""
        if state.image_url:
            return  # ya tiene imagen (seteada por LLMNode con json_output)
        for post in state.fb_posts:
            if post.get("image_url"):
                state.image_url = post["image_url"]
                logger.info("[FetchNode] fb_image: %s...", state.image_url[:60])
                break

    async def _fetch_http(self, state: FlowState) -> None:
        url     = self.config.get("url", "")
        extract = self.config.get("extract", "text")
        if not url:
            logger.warning("[FetchNode] http sin url configurada")
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                if extract == "json":
                    state.context = resp.text
                elif extract == "html":
                    state.context = resp.text
                else:
                    # extraer texto plano básico
                    import re
                    text = re.sub(r"<[^>]+>", " ", resp.text)
                    text = re.sub(r"\s+", " ", text).strip()
                    state.context = text[:5000]
            logger.info("[FetchNode] http %s: %d chars", url[:60], len(state.context))
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
                    {"value": "fb_image", "label": "Extraer imagen de posts ya cargados"},
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
                "hint":    "https://...",
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
