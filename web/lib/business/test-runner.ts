import { getDb } from "@/lib/db/client";
import { testCases, testRuns } from "@/lib/db/schema";
import { eq, asc, and, inArray } from "drizzle-orm";
import { dispatchInbound } from "@/lib/business/dispatch";
import {
  createConversation,
  getConversation,
  getChatConfigRow,
  insertUserMessage,
  listConversationMessages,
  getOwnRunSteps,
} from "@/lib/business/chats";
import { getFlow } from "@/lib/business/flows";
import { captureTestRunDiagram } from "@/lib/business/flow-capture";
import { ConversationSteps, evaluateCheck, type CheckSpec, type CheckResult, type StepDto, type TurnDto } from "@/lib/business/test-checks";
import { NotFoundError, ValidationError } from "@/lib/business/bots";

// Motor de ejecución in-process de la suite de tests configurable desde la
// UI -- puerto de `ChatConversation` (tests/e2e/helpers.py, Python + HTTP) a
// TS, pero llamando directo a `insertUserMessage`/`dispatchInbound`/DB en vez
// de hacer requests HTTP -- corre DENTRO del propio proceso de `next dev`,
// nunca contra un deployment de Vercel, así que el Local World de Workflow
// DevKit se activa solo (sin VERCEL_DEPLOYMENT_ID) y no consume cuota real
// (mismo mecanismo, mismo motivo, que ya documenta
// tests/e2e/helpers.py::resolve_chat_base_url para la suite Python vieja).

export interface TurnSpec {
  message: string;
}

export interface TestCaseDto {
  id: string;
  bot_id: string;
  chat_config_id: string;
  slug: string;
  title: string;
  description: string | null;
  turns: TurnSpec[];
  checks: CheckSpec[];
  position: number;
  created_at: Date | null;
  updated_at: Date | null;
}

type TestCaseRow = typeof testCases.$inferSelect;

function toCaseDto(row: TestCaseRow): TestCaseDto {
  return {
    id: row.id,
    bot_id: row.botId,
    chat_config_id: row.chatConfigId,
    slug: row.slug,
    title: row.title,
    description: row.description,
    turns: (row.turns as TurnSpec[]) ?? [],
    checks: (row.checks as CheckSpec[]) ?? [],
    position: row.position,
    created_at: row.createdAt,
    updated_at: row.updatedAt,
  };
}

export async function getTestCase(botId: string, caseId: string): Promise<TestCaseDto> {
  const db = getDb();
  const [row] = await db.select().from(testCases).where(eq(testCases.id, caseId));
  if (!row || row.botId !== botId) throw new NotFoundError(`Caso de test no encontrado: ${caseId}`);
  return toCaseDto(row);
}

export interface FlowSnapshotDto {
  nodes: Array<{ id: string; type: string; position: { x: number; y: number }; config?: Record<string, unknown>; label?: string }>;
  edges: Array<{ id: string; source: string; target: string; label?: string | null }>;
}

export interface TestRunResultDto {
  id: string;
  bot_id: string;
  suite_run_id: string;
  test_case_id: string;
  test_case_title: string;
  target: string;
  status: "passed" | "failed" | "error";
  turns: TurnDto[];
  check_results: CheckResult[];
  steps: StepDto[];
  flow_snapshot: FlowSnapshotDto | null;
  diagram_image: string | null;
  error_message: string | null;
  started_at: Date;
  finished_at: Date | null;
}

// Un solo turno: manda el mensaje, dispara/reanuda el flow in-process, y
// polea DB (mensajes + status del run puntual) hasta ver la respuesta del
// bot o un status terminal. Timeout generoso -- un run puede encadenar
// varios nodos LLM (mismo motivo que ChatConversation.send_and_wait, hasta
// 8m26s medido en el escenario "noticias" de Luganense).
async function runTurn(
  botId: string,
  flowId: string,
  triggerNodeId: string,
  conversationId: string,
  contactIdentifier: string,
  message: string,
  lastMessageId: number,
  timeoutMs = 480_000,
  pollIntervalMs = 3_000,
): Promise<{ reply: string | null; steps: StepDto[]; lastMessageId: number }> {
  await insertUserMessage(conversationId, message);
  const { runId } = await dispatchInbound({
    botId,
    flowId,
    triggerNodeId,
    contactIdentifier,
    message,
    canal: "chat",
  });

  const deadline = Date.now() + timeoutMs;
  let reply: string | null = null;
  let seenMessageId = lastMessageId;
  let steps: StepDto[] = [];
  let status: string | null = null;

  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, pollIntervalMs));

    const messages = await listConversationMessages(conversationId, seenMessageId);
    const botMsgs = messages.filter((m) => m.role === "bot");
    if (messages.length) seenMessageId = Math.max(...messages.map((m) => m.id));
    if (botMsgs.length) reply = botMsgs[botMsgs.length - 1].content;

    const own = await getOwnRunSteps(botId, contactIdentifier, runId);
    status = own?.status ?? null;
    steps = (own?.steps as StepDto[]) ?? steps;
    if (status === "waiting_gate" || status === "completed" || status === "error") break;
  }

  return { reply, steps, lastMessageId: seenMessageId };
}

export async function runTestCase(botId: string, caseId: string, target: "local" = "local"): Promise<TestRunResultDto> {
  const testCase = await getTestCase(botId, caseId);
  return runTestCaseDto(testCase, target, crypto.randomUUID());
}

export async function runTestCaseDto(testCase: TestCaseDto, target: "local", suiteRunId: string): Promise<TestRunResultDto> {
  const startedAt = new Date();
  const chatConfig = await getChatConfigRow(testCase.chat_config_id);
  if (!chatConfig || chatConfig.botId !== testCase.bot_id) {
    throw new ValidationError(`El chat de prueba del caso "${testCase.title}" ya no existe`);
  }

  const conv = await createConversation(testCase.bot_id, chatConfig.id, `test-case:${testCase.id}:${Date.now()}`);
  const conversationRow = await getConversation(testCase.bot_id, conv.id);
  const contactIdentifier = conversationRow!.contactIdentifier;

  const turns: TurnDto[] = [];
  const stepsAcc = new ConversationSteps();
  let lastTurnSteps: StepDto[] = [];
  let lastReply: string | null = null;
  let lastMessageId = 0;
  let errorMessage: string | null = null;

  try {
    for (const turn of testCase.turns) {
      turns.push({ role: "user", text: turn.message });
      const result = await runTurn(
        testCase.bot_id,
        chatConfig.flowId,
        chatConfig.triggerNodeId,
        conv.id,
        contactIdentifier,
        turn.message,
        lastMessageId,
      );
      lastMessageId = result.lastMessageId;
      lastReply = result.reply;
      lastTurnSteps = result.steps;
      stepsAcc.addTurnSteps(result.steps);
      turns.push({ role: "bot", text: result.reply });
    }
  } catch (err) {
    errorMessage = err instanceof Error ? err.message : String(err);
  }

  const checkResults: CheckResult[] = errorMessage
    ? []
    : testCase.checks.map((spec) =>
        evaluateCheck(spec, { conv: stepsAcc, lastTurnSteps, turns, lastReply }),
      );

  const failedAsserts = checkResults.filter((c) => c.kind === "assert" && !c.passed);
  const status: TestRunResultDto["status"] = errorMessage ? "error" : failedAsserts.length ? "failed" : "passed";
  const finishedAt = new Date();

  // Snapshot del flow tal cual estaba en el momento de la corrida -- para la
  // vista "Ver" (mini gemelo grisado con la rama resaltada), ver
  // lib/business/test-checks.ts::StepDto para el shape de `steps`.
  const flow = await getFlow(testCase.bot_id, chatConfig.flowId).catch(() => null);
  const definition = flow?.definition as { nodes?: unknown[]; edges?: unknown[] } | undefined;
  const flowSnapshot: FlowSnapshotDto | null = definition
    ? { nodes: (definition.nodes as FlowSnapshotDto["nodes"]) ?? [], edges: (definition.edges as FlowSnapshotDto["edges"]) ?? [] }
    : null;
  const steps = stepsAcc.allSteps;

  const db = getDb();
  const id = crypto.randomUUID();
  await db.insert(testRuns).values({
    id,
    botId: testCase.bot_id,
    suiteRunId,
    testCaseId: testCase.id,
    testCaseTitle: testCase.title,
    target,
    status,
    turns,
    checkResults,
    steps,
    flowSnapshot,
    errorMessage,
    startedAt,
    finishedAt,
  });

  await enforceRunRetention(testCase.bot_id).catch((err) => {
    console.error("enforceRunRetention falló (no bloquea la corrida):", err);
  });

  // Imagen del reporte -- después de insertar (necesita el `id` ya
  // persistido, EmbedTestRunPage lo lee de vuelta por HTTP) y de la
  // retención (no tiene sentido capturar una corrida que la retención
  // acaba de borrar). Best-effort: null si falla, no tira la corrida (ver
  // flow-capture.ts).
  const diagramImage = await captureTestRunDiagram(testCase.bot_id, id).catch((err) => {
    console.warn("captureTestRunDiagram falló (no bloquea la corrida):", err);
    return null;
  });
  if (diagramImage) {
    await db.update(testRuns).set({ diagramImage }).where(eq(testRuns.id, id));
  }

  return {
    id,
    bot_id: testCase.bot_id,
    suite_run_id: suiteRunId,
    test_case_id: testCase.id,
    test_case_title: testCase.title,
    target,
    status,
    turns,
    check_results: checkResults,
    steps,
    flow_snapshot: flowSnapshot,
    diagram_image: diagramImage,
    error_message: errorMessage,
    started_at: startedAt,
    finished_at: finishedAt,
  };
}

// Corre varios casos SECUENCIALMENTE (no en paralelo -- evita saturar el
// LLM local cuando corren varios escenarios de golpe; si hace falta más
// velocidad, paralelizar es un cambio contenido acá) bajo un mismo
// suite_run_id, para que la UI los pueda agrupar como "una corrida".
export async function runSuite(botId: string, caseIds?: string[]): Promise<TestRunResultDto[]> {
  const db = getDb();
  const rows = caseIds?.length
    ? await Promise.all(caseIds.map((id) => getTestCase(botId, id)))
    : (await db.select().from(testCases).where(eq(testCases.botId, botId)).orderBy(asc(testCases.position))).map(toCaseDto);

  const suiteRunId = crypto.randomUUID();
  const results: TestRunResultDto[] = [];
  for (const testCase of rows) {
    results.push(await runTestCaseDto(testCase, "local", suiteRunId));
  }
  return results;
}

// ─── Retención de corridas ──────────────────────────────────────────────
//
// Una "ejecución" = un suite_run_id (un click en "▶ Correr" o "▶ Correr
// todos"), que agrupa uno o varios test_runs. Política pedida por el
// usuario 2026-07-27:
//
//  - Del día de HOY: se guardan completas las últimas `keepToday` (10)
//    ejecuciones.
//  - De cualquier día ANTERIOR (una vez que deja de ser "hoy"): se
//    comprime a UNA sola ejecución -- la última de ese día. El resto de
//    las ejecuciones de ese día se borra. Esto pasa solo, corriendo esta
//    función después de cada corrida: el día en que cambia la fecha, la
//    próxima corrida ve el día de ayer como "pasado" y lo comprime.
//  - Se conservan como máximo `maxDays` (30) días distintos de historia
//    (contando hoy). Cualquier día más viejo que eso se borra por completo,
//    incluida su ejecución comprimida.
//
// dayKey usa UTC a propósito -- estable y determinístico para tests, sin
// depender de la timezone del proceso que corre esto (Vercel vs local).

function dayKey(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function daysBetween(a: string, b: string): number {
  const msPerDay = 24 * 60 * 60 * 1000;
  return Math.round((Date.parse(`${a}T00:00:00Z`) - Date.parse(`${b}T00:00:00Z`)) / msPerDay);
}

export interface RunRetentionRow {
  id: string;
  suiteRunId: string;
  startedAt: Date;
}

/**
 * Función pura (testeable sin DB): dado el universo de test_runs de un bot,
 * devuelve los `id` a borrar para cumplir la política de arriba.
 */
export function computeRunRetentionDeleteIds(
  rows: RunRetentionRow[],
  now: Date,
  opts: { keepToday?: number; maxDays?: number } = {},
): string[] {
  const keepToday = opts.keepToday ?? 10;
  const maxDays = opts.maxDays ?? 30;
  const today = dayKey(now);

  // Agrupar por suite_run_id -- una ejecución.
  const suites = new Map<string, { day: string; latest: number; ids: string[] }>();
  for (const row of rows) {
    const day = dayKey(row.startedAt);
    const t = row.startedAt.getTime();
    const s = suites.get(row.suiteRunId);
    if (!s) {
      suites.set(row.suiteRunId, { day, latest: t, ids: [row.id] });
    } else {
      s.ids.push(row.id);
      if (t > s.latest) s.latest = t;
    }
  }

  // Agrupar suites por día.
  const byDay = new Map<string, { suiteRunId: string; day: string; latest: number; ids: string[] }[]>();
  for (const [suiteRunId, s] of suites) {
    const list = byDay.get(s.day) ?? [];
    list.push({ suiteRunId, ...s });
    byDay.set(s.day, list);
  }

  const toDelete: string[] = [];

  for (const [day, daySuites] of byDay) {
    const age = daysBetween(today, day); // 0 = hoy, positivo = días atrás
    daySuites.sort((a, b) => b.latest - a.latest); // más reciente primero

    if (age < 0) continue; // corrida con fecha futura (reloj raro) -- no tocar
    if (age >= maxDays) {
      // Día fuera de la ventana de retención: se borra entero.
      for (const s of daySuites) toDelete.push(...s.ids);
      continue;
    }
    if (day === today) {
      // Hoy: conservar las últimas `keepToday`, borrar el resto.
      for (const s of daySuites.slice(keepToday)) toDelete.push(...s.ids);
    } else {
      // Día pasado dentro de la ventana: comprimir a la última ejecución.
      for (const s of daySuites.slice(1)) toDelete.push(...s.ids);
    }
  }

  return toDelete;
}

export async function enforceRunRetention(botId: string, now: Date = new Date()): Promise<void> {
  const db = getDb();
  const rows = await db
    .select({ id: testRuns.id, suiteRunId: testRuns.suiteRunId, startedAt: testRuns.startedAt })
    .from(testRuns)
    .where(eq(testRuns.botId, botId));
  const deleteIds = computeRunRetentionDeleteIds(rows, now);
  if (!deleteIds.length) return;
  await db.delete(testRuns).where(and(eq(testRuns.botId, botId), inArray(testRuns.id, deleteIds)));
}
