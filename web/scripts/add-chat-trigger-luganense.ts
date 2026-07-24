import { updateFlow, getFlow } from "../lib/business/flows";
import { createChatConfig, listChatConfigs } from "../lib/business/chats";

// One-off (2026-07-24, user request): agrega un nodo trigger_chat al flow
// "Orquestador Vendedor" de Luganense, en paralelo al telegram_trigger
// existente -- mismo target, mismo primer nodo downstream -- para poder
// correr el e2e (y cualquier test manual futuro) contra el flow real de
// PROD sin mandar mensajes de Telegram de verdad. No toca el
// telegram_trigger ni ningún otro nodo. Crea también el chat_config
// (privado, no listado públicamente) que el e2e usa para hablar con este
// trigger vía /api/chat/**.
//
// Correr UNA vez contra prod:
//   DATABASE_URL=<prod> DATABASE_URL_UNPOOLED=<prod> npx tsx scripts/add-chat-trigger-luganense.ts
const BOT_ID = "luganense";
const FLOW_ID = "0019d8f2-ada5-4409-99bf-50921beb875b";
const NEW_NODE_ID = "trigger_chat_e2e";

interface FlowNode {
  id: string;
  type: string;
  label?: string;
  config?: Record<string, unknown>;
  position?: { x: number; y: number };
}
interface FlowEdge {
  id: string;
  source: string;
  target: string;
  label?: string | null;
}

async function main() {
  const flow = await getFlow(BOT_ID, FLOW_ID);
  if (!flow) throw new Error(`flow ${FLOW_ID} no encontrado`);

  const definition = flow.definition as { nodes: FlowNode[]; edges: FlowEdge[] };
  if (definition.nodes.some((n) => n.id === NEW_NODE_ID)) {
    console.log(`Ya existe el nodo ${NEW_NODE_ID} -- no se toca el flow.`);
  } else {
    const telegramTrigger = definition.nodes.find((n) => n.type === "telegram_trigger");
    if (!telegramTrigger) throw new Error("telegram_trigger no encontrado en el flow");

    const outgoing = definition.edges.filter((e) => e.source === telegramTrigger.id);
    if (outgoing.length === 0) throw new Error("telegram_trigger no tiene edges salientes");

    const newNode: FlowNode = {
      id: NEW_NODE_ID,
      type: "trigger_chat",
      label: "Chat Trigger (test e2e)",
      config: {},
      position: {
        x: (telegramTrigger.position?.x ?? 0) + 260,
        y: telegramTrigger.position?.y ?? 0,
      },
    };
    const newEdges: FlowEdge[] = outgoing.map((e, i) => ({
      id: `e-chat-trigger-e2e-${i}`,
      source: NEW_NODE_ID,
      target: e.target,
      label: null,
    }));

    definition.nodes.push(newNode);
    definition.edges.push(...newEdges);

    await updateFlow(BOT_ID, FLOW_ID, { definition }, /* saveVersion */ true);
    console.log(`Nodo ${NEW_NODE_ID} agregado, con ${newEdges.length} edge(s) hacia ${outgoing.map((e) => e.target).join(", ")}`);
  }

  const existing = await listChatConfigs(BOT_ID);
  const already = existing.find((c) => c.trigger_node_id === NEW_NODE_ID);
  if (already) {
    console.log(`Ya existe chat_config ${already.id} para este trigger.`);
    return;
  }

  // isPublic:true es obligatorio -- resolveChatCaller (lib/auth/chat-access.ts)
  // solo acepta X-Chat-Visitor sin login cuando is_public=true; con false
  // devuelve 401 siempre. El chat es igual "privado" en la práctica porque
  // el id no se linkea desde ninguna UI (bug real encontrado 2026-07-24: la
  // primera versión de este script lo creaba con isPublic:false y el e2e
  // fallaba con 401 -- en prod se corrigió a mano, no vía este script).
  const chatConfig = await createChatConfig(BOT_ID, {
    flowId: FLOW_ID,
    triggerNodeId: NEW_NODE_ID,
    title: "E2E test (interno)",
    isPublic: true,
    enabled: true,
  });
  console.log("chat_config creado:", JSON.stringify(chatConfig));
}

main().then(() => process.exit(0));
