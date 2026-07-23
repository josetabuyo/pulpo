import { eq } from "drizzle-orm";
import { start } from "workflow/api";
import { getDb } from "@/lib/db/client";
import { bots, telegramConnections } from "@/lib/db/schema";
import {
  endFlowRunHandedOff,
  findMatchingTriggers,
  getWaitingGateRun,
  isKnownContact,
  restoreSlotsForResume,
  touchKnownContact,
} from "@/lib/business/telegram";
import { continueConversation } from "@/lib/flow/conversation";
import { createFlowState } from "@/lib/nodes/state";
import { runFlowWorkflow } from "@/workflows/run-flow";

// Receives Telegram Bot API webhook updates (see "Plan -- Telegram vía
// webhook" in management/HANDOFF_VERCEL_DEEP_MIGRATION.md). No session/JWT
// auth (Telegram sends neither) -- verification is the tokenId in the URL
// itself, plus an optional `secret_token` header if TELEGRAM_WEBHOOK_SECRET
// is set (see setWebhook call, step 4 of the plan). proxy.ts exempts this
// path from the normal auth gate.
//
// Always responds 200 unless tokenId itself is unknown -- Telegram retries
// aggressively on non-2xx, and update types we don't handle (edited
// messages, callback queries, etc.) aren't errors.
export async function POST(request: Request, { params }: { params: Promise<{ tokenId: string }> }) {
  const { tokenId } = await params;
  const db = getDb();

  const [conn] = await db.select().from(telegramConnections).where(eq(telegramConnections.tokenId, tokenId));
  if (!conn) return Response.json({ error: "unknown token" }, { status: 404 });

  const secret = process.env.TELEGRAM_WEBHOOK_SECRET;
  if (secret && request.headers.get("x-telegram-bot-api-secret-token") !== secret) {
    return Response.json({ error: "invalid secret token" }, { status: 401 });
  }

  const update = await request.json().catch(() => null);
  const message = update?.message;
  const text: string = message?.text ?? "";
  if (!message?.chat?.id || !text) {
    return Response.json({ ok: true });
  }

  const [bot] = await db.select().from(bots).where(eq(bots.id, conn.botId));
  if (!bot) return Response.json({ ok: true }); // conexión huérfana -- no debería pasar

  // TS port simplificado de pulpo/core/paused.py: el original sigue
  // corriendo el flow completo (para side effects como summarize) pero
  // suprime el reply. Acá directamente no se dispatchea nada -- más simple,
  // y suficiente mientras nada dependa de esos side effects en Vercel.
  if (bot.paused) return Response.json({ ok: true, paused: true });

  const chatId = String(message.chat.id);
  const username: string | undefined = message.from?.username;
  const firstName: string = message.from?.first_name ?? "";
  // "{botId}-tg-{tokenId}" -- ver lib/business/bots.ts::listBots(), es lo que
  // un nodo telegram_trigger realmente guarda en config.connection_id.
  const sessionId = `${bot.id}-tg-${tokenId}`;

  const known = await isKnownContact(tokenId, chatId);
  await touchKnownContact(tokenId, chatId, username ?? null, firstName || null);

  const baseState = () =>
    createFlowState({
      message: text,
      canal: "telegram",
      botId: bot.id,
      botName: bot.name,
      connectionId: sessionId,
      contactPhone: chatId,
      contactName: firstName || username || "",
      timestamp: new Date((message.date ?? Date.now() / 1000) * 1000).toISOString(),
    });

  // ── Dispatcher wait_user: reanudar conversación pausada (TS port de la
  // mitad "dispatcher" de dispatch_message, pulpo/graphs/compiler.py) ────────
  const waiting = await getWaitingGateRun(bot.id, chatId);
  if (waiting && waiting.resumeNodeId) {
    const resumeState = baseState();
    resumeState.data = restoreSlotsForResume(waiting.slotsJson, waiting.startedAt ?? new Date());
    continueConversation(resumeState);
    await endFlowRunHandedOff(waiting.runId);
    await start(runFlowWorkflow, [waiting.flowId, waiting.resumeNodeId, resumeState]);
    return Response.json({ ok: true, resumed: true });
  }

  const matches = await findMatchingTriggers(bot.id, tokenId, chatId, text, known, conn.allowMass);

  for (const match of matches) {
    await start(runFlowWorkflow, [match.flowId, match.nodeId, baseState()]);
  }

  return Response.json({ ok: true, matched: matches.length });
}
