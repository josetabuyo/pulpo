import type { NodeDef } from "./base";
import { interpolate } from "./interpolate";
import { waviGet, waviSend } from "./wavi-client";

// Two node types wrapping Wavi's local WhatsApp Web server (see
// wavi-client.ts and management/HANDOFF_LOCAL_CLI_AND_NODES.md §3.1).
// `list-contacts`/`check-updates`/`status` are deliberately NOT exposed as
// node types yet -- no flow needs them; add when a real consumer shows up
// (same "regla de tres" already applied to contacts/messages in the
// migration, see HANDOFF_VERCEL_DEEP_MIGRATION.md).
//
// wavi_send sends a REAL WhatsApp message through whatever session is
// logged into Chromium on this Mac -- unlike the local Postgres seed (no
// Telegram token, so it's impossible to send for real by accident), the
// isolation here depends entirely on which Wavi session is authenticated.
// `session` defaults to "default", which may be a personal/real session --
// never hardcode a production session id here, and prefer a throwaway test
// contact when exercising this node.
export const waviSendNode: NodeDef = {
  label: "WhatsApp local (Wavi)",
  color: "#25d366",
  description: "Envía un mensaje de WhatsApp real vía Wavi (Chromium local) -- solo dev local, en producción no hace nada.",
  configSchema: {
    session: { type: "string", label: "Sesión de Wavi", default: "default", hint: "Sesión de Chromium logueada en Wavi -- ⚠️ puede ser tu WhatsApp personal, no uses un contacto real de cliente para probar." },
    contact: { type: "string", label: "Contacto", required: true, hint: "Nombre/número tal como lo resuelve Wavi. Interpolable, ej: {{contact_phone}}." },
    message: { type: "string", label: "Mensaje", required: true, hint: "Interpolable." },
    output: { type: "string", label: "Guardar resultado en", default: "wavi_result" },
  },
  async run(state, config) {
    if (state.fromDeltaSync) return state;

    const session = interpolate((config.session as string) ?? "default", state) || "default";
    const contact = interpolate((config.contact as string) ?? "", state);
    const message = interpolate((config.message as string) ?? "", state);
    const output = interpolate((config.output as string) ?? "wavi_result", state);

    const { ok, data, error } = await waviSend({ session, contact, message });
    if (ok) {
      state.data[output] = data;
    } else {
      console.warn(`[wavi_send] ${error}`);
      state.data._wavi_errors = [...((state.data._wavi_errors as unknown[]) ?? []), { node: "wavi_send", error }];
    }
    return state;
  },
};

export const waviGetNode: NodeDef = {
  label: "Leer WhatsApp local (Wavi)",
  color: "#25d366",
  description: "Trae mensajes de una conversación de WhatsApp real vía Wavi -- solo dev local, en producción no hace nada.",
  configSchema: {
    session: { type: "string", label: "Sesión de Wavi", default: "default" },
    contact: { type: "string", label: "Contacto", required: true, hint: "Interpolable, ej: {{contact_phone}}." },
    newest: { type: "float", label: "Solo mensajes más nuevos que (timestamp, opcional)" },
    output: { type: "string", label: "Guardar burbujas en", default: "wavi_messages" },
  },
  async run(state, config) {
    if (state.fromDeltaSync) return state;

    const session = interpolate((config.session as string) ?? "default", state) || "default";
    const contact = interpolate((config.contact as string) ?? "", state);
    const output = interpolate((config.output as string) ?? "wavi_messages", state);
    const newest = config.newest !== undefined && config.newest !== null ? Number(config.newest) : undefined;

    const { ok, data, error } = await waviGet({ session, contact, newest });
    if (ok && data) {
      state.data[output] = data.bubbles;
    } else {
      console.warn(`[wavi_get] ${error}`);
      state.data._wavi_errors = [...((state.data._wavi_errors as unknown[]) ?? []), { node: "wavi_get", error }];
    }
    return state;
  },
};
