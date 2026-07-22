import type { NodeDef } from "./base";
import { interpolate } from "./interpolate";
import { recordBotReply } from "./state";

// TS port of SendMessageNode (pulpo/graphs/nodes/reply.py). Scoped down:
// only the `to` empty case (reply to the user who triggered the flow) is
// implemented -- it just writes state.data.reply, same as Python, and the
// HTTP/workflow caller is responsible for actually delivering it (matches
// how api_trigger's HTTP response already works today). Sending to a third
// party (`to` set, e.g. a Telegram broadcast) requires the Telegram driver
// port (webhook + Bot API calls) that's still pending -- see handoff doc.
// When `to` is set, this logs and no-ops instead of silently pretending to
// send.
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
      return state;
    }

    console.warn(
      `[reply] envío a terceros (to=${to}) no implementado todavía en web/ -- requiere el driver de Telegram (webhook), pendiente`,
    );
    return state;
  },
};
