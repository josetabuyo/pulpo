// Ubicación del visitante del chat, detectada por IP -- reemplaza el
// default fijo del banner "info trans" (ver InfoBanner.jsx, lib/business/
// chats.ts::DEFAULT_BANNER_LOCATION) por la ubicación real de quien está
// usando el chat en ese momento. IP-based (no navigator.geolocation): no
// pide permiso al visitante, funciona para todos sin fricción, aunque sea
// menos preciso que GPS (a nivel ciudad/barrio). ipwho.is: gratis, sin API
// key, HTTPS. Server-side porque el IP real del visitante solo está
// disponible en los headers de la request (x-forwarded-for), no en el
// browser.
//
// Dinámico a propósito (no revalidate estático como /api/weather) -- el IP
// cambia por visitante, cachear acá pisaría la ubicación de uno con la de
// otro.
export const dynamic = "force-dynamic";

function extractIp(request: Request): string | null {
  const xff = request.headers.get("x-forwarded-for");
  if (xff) {
    const first = xff.split(",")[0]?.trim();
    if (first) return first;
  }
  return request.headers.get("x-real-ip");
}

// localhost/dev y redes privadas no tienen un IP público geolocalizable --
// dejamos que ipwho.is use el IP de salida del server en vez de pasarle un
// IP privado que le va a devolver error.
function isPrivateIp(ip: string): boolean {
  return (
    ip === "127.0.0.1" ||
    ip === "::1" ||
    ip.startsWith("10.") ||
    ip.startsWith("192.168.") ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(ip)
  );
}

export async function GET(request: Request) {
  const ip = extractIp(request);
  const target = ip && !isPrivateIp(ip) ? ip : "";

  try {
    const res = await fetch(`https://ipwho.is/${target}`);
    if (!res.ok) throw new Error(`ipwho.is respondió ${res.status}`);
    const data = await res.json();
    if (!data?.success) throw new Error(data?.message || "ipwho.is sin éxito");

    const lat = data.latitude;
    const lon = data.longitude;
    const timezone = data.timezone?.id;
    if (typeof lat !== "number" || typeof lon !== "number" || !timezone) {
      throw new Error("respuesta de ipwho.is incompleta");
    }

    const label = [data.city, data.region].filter(Boolean).join(", ") || data.country || "Ubicación detectada";
    return Response.json({ label, timezone, lat, lon });
  } catch (err) {
    console.error("[geo]", err);
    return Response.json({ error: "no se pudo geolocalizar" }, { status: 200 });
  }
}
