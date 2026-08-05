import { regenerateBotApiKey } from "@/lib/business/bots";
import { errorResponse } from "@/lib/api/errors";
import { assertBotAccess } from "@/lib/auth/bot-access";

// Genera/rota el secreto que un sistema externo (el CMS propio del cliente)
// usa para publicar publicidad en sus chats -- ver lib/auth/bot-key.ts. El
// valor en claro solo se devuelve UNA vez, en esta respuesta (mismo criterio
// que /api/auth/token con el bearer JWT); el resto de la UI lo muestra
// enmascarado y ofrece "Regenerar", que vuelve a llamar acá.
export async function POST(request: Request, { params }: { params: Promise<{ botId: string }> }) {
  const { botId } = await params;
  const denied = await assertBotAccess(request, botId);
  if (denied) return denied;
  try {
    const apiKey = await regenerateBotApiKey(botId);
    return Response.json({ api_key: apiKey });
  } catch (err) {
    return errorResponse(err);
  }
}
