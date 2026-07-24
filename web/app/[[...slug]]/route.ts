import { SPA_INDEX_HTML } from "@/lib/generated/spa-index";

// Catch-all de la SPA (2026-07-24, "un solo deploy"): sirve el index.html
// de frontend/ (React Router hace el ruteo del lado del cliente) para
// cualquier path que no matchee algo más específico. `/api/**` y
// `/.well-known/workflow/**` son subcarpetas literales de app/ -- Next.js
// las resuelve antes de caer acá, nunca hay conflicto. Los assets
// estáticos (public/assets/**) los sirve Vercel directo desde el CDN, sin
// pasar por esta función.
export async function GET() {
  return new Response(SPA_INDEX_HTML, {
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}
