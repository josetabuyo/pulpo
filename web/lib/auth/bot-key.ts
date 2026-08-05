import crypto from "node:crypto";
import { getBotApiKey } from "@/lib/business/bots";

// Sexto esquema de auth (2026-08-05, publicidad de chat -- ver
// lib/business/chat-ads.ts): header `X-Pulpo-Bot-Key` comparado en tiempo
// constante contra `bots.apiKey` de ESE botId puntual. A diferencia de
// lib/auth/sync-token.ts (un secreto global de instancia, para que OTRO
// ambiente Pulpo llame), este es un secreto por-bot, pensado para que el
// sistema propio de UN cliente (su CMS/ABM de publicidad) llame solo a los
// endpoints de publish/unpublish de SU bot -- nunca autoriza nada más.
export async function isBotKeyRequest(request: Request, botId: string): Promise<boolean> {
  const provided = request.headers.get("x-pulpo-bot-key");
  if (!provided) return false;
  const expected = await getBotApiKey(botId);
  if (!expected) return false;
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}
