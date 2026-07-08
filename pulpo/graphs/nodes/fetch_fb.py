"""
FetchFbNode — scrapea posts de una página de Facebook y guarda el resultado en
state.data["context"] (+ state.data["fb_posts"] y state.data["source_urls"]).

Config:
  fb_page_id:    str — slug de la página de Facebook (si vacío, usa state.bot_id)
  fb_numeric_id: str — ID numérico de la página (opcional, habilita búsqueda directa)
"""
import asyncio
import logging

from .base import BaseNode
from .state import FlowState

logger = logging.getLogger(__name__)


class FetchFbNode(BaseNode):
    label = "Buscar Facebook"
    color = "#1877f2"
    description = "Scrapea posts de una página de Facebook para usar como contexto."

    async def run(self, state: FlowState) -> FlowState:
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
            from pulpo.tools.facebook import fetch_facebook

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
            logger.info("[FetchFbNode] %d posts, %d chars", len(fb_posts), len(context))

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
            logger.error("[FetchFbNode] Error fetching Facebook: %s", e)

        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "fb_page_id": {
                "type":    "string",
                "label":   "Página de Facebook (slug)",
                "default": "",
                "hint":    "ej: luganense, cnn, tuportal",
            },
            "fb_numeric_id": {
                "type":    "string",
                "label":   "ID numérico FB (opcional)",
                "default": "",
                "hint":    "Habilita búsqueda directa. Ej: 100070998865103",
            },
        }
