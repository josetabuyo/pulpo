import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { telegramConnections } from "@/lib/db/schema";
import { sendTelegramMessage } from "@/lib/business/telegram";
import type { NodeDef } from "./base";
import { interpolate } from "./interpolate";
import { recordBotReply } from "./state";

// TS port of SendMessageNode (pulpo/graphs/nodes/reply.py). Scoped down:
// only the `to` empty case (reply to the user who triggered the flow) is
// implemented. For canal === "telegram" (webhook path, see
// app/api/telegram/webhook/[tokenId]/route.ts) this now actually calls the
// Telegram Bot API -- there's no HTTP response the way api_trigger has one,
// so somebody has to push the reply out. For other canales (api_trigger),
// behavior is unchanged: just writes state.data.reply, and the caller
// inspects it via flow_run_steps. Sending to a third party (`to` set, e.g.
// a Telegram broadcast to someone other than whoever triggered the flow) is
// still not implemented -- logs and no-ops instead of silently pretending
// to send.
export const replyNode: NodeDef = {
  label: "Enviar mensaje",
  color: "#15803d",
  description: "Envía un mensaje al usuario o a un contacto externo vía Telegram.",
  configSchema: {},
  async run(state, config) {
    if (state.fromDeltaSync) return state;

    const to = interpolate((config.to as string) ?? "", state).trim();
    const message = interpolate((config.message as string) ?? "", state);

    if (!to) {
      const maxAge = Number(config.max_age_hours ?? 1.0);
      if (maxAge > 0 && state.timestamp) {
        const ageHours = (Date.now() - new Date(state.timestamp).getTime()) / 3_600_000;
        if (ageHours > maxAge) {
          return state;
        }
      }
      state.data.reply = message;
      recordBotReply(state, message);

      if (state.canal === "telegram" && state.connectionId && message) {
        try {
          // state.connectionId is the session id "{botId}-tg-{tokenId}" (see
          // lib/business/telegram.ts's connectionMatches) -- telegram_connections
          // is keyed by the bare tokenId, so recover it from the tail.
          const tokenId = state.connectionId.split("-tg-").pop() ?? state.connectionId;
          const db = getDb();
          const [conn] = await db
            .select()
            .from(telegramConnections)
            .where(eq(telegramConnections.tokenId, tokenId));
          if (conn) {
            await sendTelegramMessage(conn.token, state.contactPhone, message);
          } else {
            console.error(`[reply] telegram_connections sin fila para tokenId=${state.connectionId}`);
          }
        } catch (err) {
          console.error("[reply] falló el envío a Telegram (no aborta el flow)", err);
        }
      }
      return state;
    }

    console.warn(
      `[reply] envío a terceros (to=${to}) no implementado todavía en web/ -- requiere resolver otro chat_id que el que disparó el flow, pendiente`,
    );
    return state;
  },
};
