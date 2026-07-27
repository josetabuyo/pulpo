import { getEnvironment } from "@/lib/business/environments";
import { getFlow, updateFlow } from "@/lib/business/flows";
import { NotFoundError, ValidationError } from "@/lib/business/bots";

// Contraparte HTTP de scripts/sync-flow.ts (DB directa, fallback de
// emergencia) -- usado tanto por el botón "Sync" del editor de flows como,
// indirectamente, por la misma lógica que cli/main.ts::flows sync ya
// ejercita. A diferencia del CLI (que resuelve el ambiente vía
// GET /api/environments/{name}, que SÍ incluye admin_token en la respuesta
// porque el caller es un proceso Node de confianza), acá el admin_token
// nunca sale de este proceso -- el browser solo ve name/definition/diff.

export type SyncDirection = "pull" | "push";

export function parseSyncDirection(value: unknown): SyncDirection {
  if (value !== "pull" && value !== "push") {
    throw new ValidationError(`direction inválido: ${JSON.stringify(value)} (esperado "pull" o "push")`);
  }
  return value;
}

interface FlowSide {
  name: string;
  definition: unknown;
}

async function remoteFlowFetch(
  baseUrl: string,
  token: string,
  botId: string,
  flowId: string,
  init?: RequestInit,
): Promise<FlowSide> {
  let res: Response;
  try {
    res = await fetch(`${baseUrl}/api/flows/bots/${botId}/${flowId}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-Pulpo-Sync-Token": token, ...(init?.headers ?? {}) },
    });
  } catch (err) {
    throw new ValidationError(`No se pudo conectar a ${baseUrl}: ${err instanceof Error ? err.message : String(err)}`);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ValidationError(
      `El ambiente remoto respondió ${res.status}: ${body && typeof body === "object" && "detail" in body ? body.detail : JSON.stringify(body)}`,
    );
  }
  return { name: body.name, definition: body.definition };
}

async function readLocalFlow(botId: string, flowId: string): Promise<FlowSide> {
  const flow = await getFlow(botId, flowId);
  if (!flow) throw new NotFoundError(`Flow no encontrado: ${flowId}`);
  return { name: flow.name, definition: flow.definition };
}

async function readSide(
  direction: SyncDirection,
  side: "source" | "target",
  botId: string,
  flowId: string,
  env: { base_url: string; admin_token: string },
): Promise<FlowSide> {
  const isRemote = (direction === "pull" && side === "source") || (direction === "push" && side === "target");
  if (isRemote) return remoteFlowFetch(env.base_url, env.admin_token, botId, flowId);
  return readLocalFlow(botId, flowId);
}

export async function diffEnvironmentFlow(envName: string, botId: string, flowId: string, direction: SyncDirection) {
  const env = await getEnvironment(envName);
  const [source, target] = await Promise.all([
    readSide(direction, "source", botId, flowId, env),
    readSide(direction, "target", botId, flowId, env),
  ]);
  return {
    source_name: source.name,
    source_definition: source.definition,
    target_name: target.name,
    target_definition: target.definition,
    identical: JSON.stringify(source.definition) === JSON.stringify(target.definition),
  };
}

// active:false SIEMPRE en el destino -- mismo motivo que scripts/sync-flow.ts
// y cli/main.ts::flows sync: un flow traído de otro ambiente no debe
// arrancar a disparar solo porque comparte connection_id con lo que ya
// corría ahí. Guarda la definición previa del destino como flow_version
// antes de pisarla (save_version:true / saveVersion=true).
export async function applyEnvironmentFlowSync(envName: string, botId: string, flowId: string, direction: SyncDirection) {
  const env = await getEnvironment(envName);
  const source = await readSide(direction, "source", botId, flowId, env);

  if (direction === "pull") {
    const updated = await updateFlow(
      botId,
      flowId,
      { name: source.name, definition: source.definition as Record<string, unknown>, active: false },
      true,
    );
    if (!updated) throw new NotFoundError(`Flow no encontrado: ${flowId}`);
    return updated;
  }

  await remoteFlowFetch(env.base_url, env.admin_token, botId, flowId, {
    method: "PUT",
    body: JSON.stringify({ name: source.name, definition: source.definition, active: false, save_version: true }),
  });
  return { ok: true };
}
