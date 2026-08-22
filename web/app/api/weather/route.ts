// Temperatura actual de un punto (lat/lon) para el banner "info trans" del
// chat (ver InfoBanner.jsx en frontend/). Genérico a propósito -- cada chat
// configura su propia ubicación en chat_configs.info_banner.location (ver
// lib/business/chats.ts::DEFAULT_BANNER_LOCATION, Lugano es solo el default
// del primer cliente, no algo hardcodeado acá). Open-Meteo: gratis, sin API
// key. Server-side a propósito -- así todos los visitantes de un mismo chat
// comparten la misma respuesta cacheada en vez de que cada browser le pegue
// directo.

// Debe ser un literal -- Next.js parsea este export estáticamente (build
// falla con "Invalid segment configuration export" si es una referencia a
// una const, aunque el valor final sea el mismo).
export const revalidate = 600;

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const latParam = searchParams.get("lat");
  const lonParam = searchParams.get("lon");
  const lat = latParam === null ? NaN : Number(latParam);
  const lon = lonParam === null ? NaN : Number(lonParam);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    return Response.json({ error: "lat/lon inválidos" }, { status: 400 });
  }

  const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m`;
  try {
    const res = await fetch(url, { next: { revalidate: 600 } });
    if (!res.ok) throw new Error(`open-meteo respondió ${res.status}`);
    const data = await res.json();
    const temp = data?.current?.temperature_2m;
    if (typeof temp !== "number") throw new Error("respuesta sin temperature_2m");
    return Response.json({ temperature_c: temp });
  } catch (err) {
    console.error("[weather]", err);
    return Response.json({ temperature_c: null }, { status: 200 });
  }
}
