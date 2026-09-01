import crypto from "node:crypto";
import { createBot } from "../lib/business/bots";
import { getFlow } from "../lib/business/flows";
import { getDb } from "../lib/db/client";
import { flows } from "../lib/db/schema";
import { createChatConfig, listChatConfigs, updateChatConfig } from "../lib/business/chats";

// Bootstrap idempotente del bot "machelectronics" -- pensado para correr
// contra CUALQUIER DATABASE_URL (local hoy, prod más adelante) y dejar el
// mismo bot_id/flow_id/chat_config en ambos lados, mismo patrón que
// scripts/add-chat-trigger-luganense.ts + scripts/seed-flow.ts. Después de
// este seed, iterar el contenido del flow va por el editor + sync-flow.ts
// (--direction push), NO reescribiendo este script (ver
// management/HANDOFF_WORKFLOW_LOCAL_DEV.md).
//
// Flow v2 (2026-09-01): trigger_chat -> document_vision -> llm -> send_message.
// document_vision (lib/nodes/document-vision.ts) lee la imagen adjunta
// ({{attachment_url}}, seteado por dispatchInbound vía data.attachment_url
// cuando el usuario manda una foto, ver app/api/chat/.../messages/route.ts)
// con un LLM con visión y deja el JSON extraído en state.data.document_data
// -- null si el mensaje no traía adjunto (no-opea, no llama a ningún
// provider). El LLM de después arma la respuesta según haya o no datos.
// Todavía quedan "solo anotadas" (no implementadas) las otras 4 piezas de
// management/PLAN_NODOS_PENDIENTES_MACH.md (trigger de email, aritmética,
// DB read-only, gate durable).
//
// Uso:
//   npx dotenv -e .env.local -- npx tsx scripts/seed-machelectronics.ts   (local)
//   DATABASE_URL=<neon-prod> npx tsx scripts/seed-machelectronics.ts      (prod, más adelante)
const BOT_ID = "machelectronics";
const BOT_NAME = "MachElectronics";
const FLOW_ID = "8f1e6f6a-7b3e-4b1a-9c2d-6a9c9e8f4d10";
const TRIGGER_NODE_ID = "trigger1";

const VISION_PROMPT = `Esto es una foto o escaneo de una factura o ticket de compra.

Extraé, si están legibles, estos campos: proveedor (nombre de quien emite), cuit (del emisor), numero (número de comprobante), fecha (de emisión), importe_total.

Devolvé un JSON con exactamente esas 5 claves. Si no podés leer un campo con confianza, dejalo en null -- nunca inventes un valor ni completes con un dato que no está en la imagen.`;

const SYSTEM_PROMPT = `Sos el asistente de carga de facturas de MachElectronics.

Tenés disponible {{document_data}}: el resultado (JSON o null) de intentar leer la factura adjunta con un modelo de visión.

Si {{document_data}} es null: pedí amablemente que suban la foto o imagen de la factura para poder recibirla. Nada más, en una frase.

Si {{document_data}} NO es null: agradecé que mandaron la factura y devolvé los campos leídos EN LISTA, uno por línea, con este formato exacto (una línea por campo, "Etiqueta: valor"):

Proveedor: <valor>
CUIT: <valor>
Número: <valor>
Fecha: <valor>
Importe: <valor>

Omití por completo la línea de cualquier campo que haya venido null en {{document_data}} -- no la incluyas ni con "no disponible", directamente no la escribas. Nunca inventes un valor que no esté en {{document_data}}. Después de la lista, agregá una línea aparte aclarando que está en proceso.

Respondé siempre en español, tono profesional y directo. No agregues nada fuera de lo pedido arriba.`;

function buildDefinition() {
  return {
    nodes: [
      { id: TRIGGER_NODE_ID, type: "trigger_chat", label: "Chat Trigger", config: {}, position: { x: 0, y: 0 } },
      {
        id: "vision1",
        type: "document_vision",
        label: "Lector de documentos (visión)",
        config: {
          prompt: VISION_PROMPT,
          image_url: "{{attachment_url}}",
          output: "document_data",
          temperature: 0.1,
          max_tokens: 500,
        },
        position: { x: 260, y: 0 },
      },
      {
        id: "llm1",
        type: "llm",
        label: "Respuesta LLM",
        config: {
          prompt: SYSTEM_PROMPT,
          model: "best:instruction",
          temperature: 0.3,
          output: "reply",
          json_output: false,
          output_as_list: false,
        },
        position: { x: 520, y: 0 },
      },
      {
        // El nodo `llm` solo escribe state.data.reply -- no manda nada solo.
        // Quien realmente inserta el mensaje bot en chat_messages (canal
        // "chat") es send_message/replyNode (lib/nodes/reply.ts), acá con
        // `to` vacío = responde al usuario que disparó el flow. Sin este
        // nodo, el LLM corre pero el chat nunca ve la respuesta (bug real
        // encontrado probando en local, 2026-09-01).
        id: "send1",
        type: "send_message",
        label: "Enviar mensaje",
        config: { to: "", message: "{{reply}}", channel: "telegram", max_age_hours: 1.0 },
        position: { x: 780, y: 0 },
      },
    ],
    edges: [
      { id: "e-trigger-vision", source: TRIGGER_NODE_ID, target: "vision1", label: null },
      { id: "e-vision-llm", source: "vision1", target: "llm1", label: null },
      { id: "e-llm-send", source: "llm1", target: "send1", label: null },
    ],
  };
}

async function ensureBot() {
  try {
    const password = crypto.randomBytes(9).toString("base64url");
    await createBot(BOT_ID, BOT_NAME, password);
    console.log(`Bot creado: ${BOT_ID} -- password admin: ${password} (guardala, no se vuelve a mostrar)`);
  } catch (e) {
    if ((e as Error).name === "ConflictError" || /Ya existe/.test((e as Error).message ?? "")) {
      console.log(`Bot ya existía: ${BOT_ID} -- no se toca.`);
    } else {
      throw e;
    }
  }
}

async function ensureFlow() {
  const existing = await getFlow(BOT_ID, FLOW_ID);
  if (existing) {
    console.log(`Flow ya existía: ${FLOW_ID} -- no se pisa (editar por el dashboard + sync-flow.ts).`);
    return;
  }
  const db = getDb();
  await db.insert(flows).values({
    id: FLOW_ID,
    botId: BOT_ID,
    name: "MachElectronics — Recepción de facturas (v1)",
    active: false,
    definition: buildDefinition(),
  });
  console.log(`Flow creado: ${FLOW_ID} (queda active:false -- activalo a mano desde el dashboard tras probarlo).`);
}

// "Chat pelado" que pidió José: sin banner de clima/ubicación (toInfoBannerDto
// en lib/business/chats.ts default a enabled:true si no se pasa nada
// explícito -- hay que apagarlo a mano) y sin ninguna fila en chat_ads (no
// se crea ninguna acá, así que no hay publicidad).
const BARE_CONFIG = {
  flowId: FLOW_ID,
  triggerNodeId: TRIGGER_NODE_ID,
  title: "MachElectronics",
  isPublic: true,
  enabled: true,
  infoBanner: { enabled: false },
  adsEnabled: false,
  sidebarEnabled: false,
};

async function ensureChatConfig() {
  const existing = await listChatConfigs(BOT_ID);
  const already = existing.find((c) => c.trigger_node_id === TRIGGER_NODE_ID && c.flow_id === FLOW_ID);
  if (already) {
    await updateChatConfig(already.id, BOT_ID, BARE_CONFIG);
    console.log(`chat_config ya existía: ${already.id} -- banner de clima/ubicación forzado a apagado.`);
    return;
  }
  const chatConfig = await createChatConfig(BOT_ID, BARE_CONFIG);
  console.log(`chat_config creado: ${JSON.stringify(chatConfig)}`);
}

async function main() {
  await ensureBot();
  await ensureFlow();
  await ensureChatConfig();
}

main().then(() => process.exit(0));
