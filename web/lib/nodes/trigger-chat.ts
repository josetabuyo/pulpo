import type { NodeDef } from "./base";

// Punto de entrada para mensajes desde un chat de la tab "Chats"
// (PulpoChat, 2026-07-23). Nodo propio, separado de telegram_trigger a
// propósito (pedido explícito del usuario: "cada cosa separada
// correctamente según su responsabilidad") -- no pasa por
// findMatchingTriggers/matching en tiempo de ejecución como Telegram: el
// ruteo es explícito, fijado por chat_configs.flow_id/trigger_node_id al
// crear el chat (ver lib/business/chats.ts). El campo `chat_id` de su
// config es solo informativo (a qué chat pertenece este nodo en el
// editor), no un mecanismo de matching.
//
// Un flow puede tener un telegram_trigger y un trigger_chat en paralelo,
// cada uno disparando el mismo flow por su propio canal, sin interferirse
// (mismo criterio que el usuario pidió replicar en Luganense).
const triggerChatNode: NodeDef = {
  label: "Chat Trigger",
  color: "#7c3aed",
  description: "Punto de entrada para mensajes desde un chat de la tab Chats.",
  configSchema: {},
  async run(state) {
    return state;
  },
};

export { triggerChatNode };
