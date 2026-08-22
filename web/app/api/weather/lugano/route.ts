// Temperatura actual de Lugano para el banner "info trans" del chat (ver
// InfoBanner.jsx en frontend/). Open-Meteo: gratis, sin API key. Server-side
// a propósito -- así todos los visitantes del chat comparten la misma
// respuesta cacheada en vez de que cada browser le pegue directo.
const LUGANO_LAT = 46.0037;
const LUGANO_LON = 8.9511;

// Debe ser un literal -- Next.js parsea este export estáticamente (build
// falla con "Invalid segment configuration export" si es una referencia a
// una const, aunque el valor final sea el mismo).
export const revalidate = 600;

export async function GET() {
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${LUGANO_LAT}&longitude=${LUGANO_LON}&current=temperature_2m&timezone=Europe%2FZurich`;
  try {
    const res = await fetch(url, { next: { revalidate: 600 } });
    if (!res.ok) throw new Error(`open-meteo respondió ${res.status}`);
    const data = await res.json();
    const temp = data?.current?.temperature_2m;
    if (typeof temp !== "number") throw new Error("respuesta sin temperature_2m");
    return Response.json({ temperature_c: temp });
  } catch (err) {
    console.error("[weather/lugano]", err);
    return Response.json({ temperature_c: null }, { status: 200 });
  }
}
