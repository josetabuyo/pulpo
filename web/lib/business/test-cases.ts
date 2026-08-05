import { and, asc, desc, eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { bots, chatConfigs, testCases, testRuns } from "@/lib/db/schema";
import { NotFoundError, ValidationError } from "@/lib/business/bots";
import type { CheckSpec } from "@/lib/business/test-checks";
import type { TurnSpec } from "@/lib/business/test-runner";

// CRUD de casos de test (tab "Test" > "Casos", ver
// /Users/josetabuyo/.claude/plans/iridescent-whistling-blossom.md). `turns`/
// `checks` viajan como el documento JSON completo -- se editan siempre
// juntos desde el editor de la UI, mismo patrón que
// chatConfigs.banners/themeVars (ver lib/business/chats.ts).

type TestCaseRow = typeof testCases.$inferSelect;

function toDto(row: TestCaseRow) {
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

export interface TestCaseInput {
  chatConfigId: string;
  slug: string;
  title: string;
  description?: string;
  turns: TurnSpec[];
  checks: CheckSpec[];
  position?: number;
}

function validateInput(input: TestCaseInput) {
  if (!input.chatConfigId) throw new ValidationError("chat_config_id es requerido");
  if (!input.slug?.trim()) throw new ValidationError("slug es requerido");
  if (!input.title?.trim()) throw new ValidationError("title es requerido");
  if (!Array.isArray(input.turns) || input.turns.length === 0) {
    throw new ValidationError("El caso necesita al menos un turno");
  }
  for (const t of input.turns) {
    if (!t.message?.trim()) throw new ValidationError("Todos los turnos necesitan un mensaje");
  }
  if (!Array.isArray(input.checks)) throw new ValidationError("checks debe ser una lista");
}

// Estado de la corrida más reciente por caso -- alimenta el badge que la
// lista de "Casos" muestra a primera vista (ver TestCasesTab.jsx), para ir
// directo al caso con problemas sin tener que entrar a cada uno.
interface LatestRunSummary {
  id: string;
  status: string;
  started_at: Date | null;
  failed_checks: number;
}

async function getLatestRunSummaries(botId: string): Promise<Map<string, LatestRunSummary>> {
  const db = getDb();
  const rows = await db
    .select({
      id: testRuns.id,
      testCaseId: testRuns.testCaseId,
      status: testRuns.status,
      startedAt: testRuns.startedAt,
      checkResults: testRuns.checkResults,
    })
    .from(testRuns)
    .where(eq(testRuns.botId, botId))
    .orderBy(desc(testRuns.startedAt));

  const latest = new Map<string, LatestRunSummary>();
  for (const r of rows) {
    if (latest.has(r.testCaseId)) continue;
    const checks = (r.checkResults as { kind: string; passed: boolean }[]) ?? [];
    latest.set(r.testCaseId, {
      id: r.id,
      status: r.status,
      started_at: r.startedAt,
      failed_checks: checks.filter((c) => c.kind === "assert" && !c.passed).length,
    });
  }
  return latest;
}

export async function listTestCases(botId: string) {
  const db = getDb();
  const rows = await db.select().from(testCases).where(eq(testCases.botId, botId)).orderBy(asc(testCases.position));
  const latestRuns = await getLatestRunSummaries(botId);
  return rows.map((row) => ({ ...toDto(row), latest_run: latestRuns.get(row.id) ?? null }));
}

export async function getTestCaseRow(botId: string, caseId: string): Promise<TestCaseRow> {
  const db = getDb();
  const [row] = await db.select().from(testCases).where(eq(testCases.id, caseId));
  if (!row || row.botId !== botId) throw new NotFoundError(`Caso de test no encontrado: ${caseId}`);
  return row;
}

export async function getTestCaseDto(botId: string, caseId: string) {
  return toDto(await getTestCaseRow(botId, caseId));
}

async function assertChatConfigBelongsToBot(botId: string, chatConfigId: string) {
  const db = getDb();
  const [row] = await db.select().from(chatConfigs).where(eq(chatConfigs.id, chatConfigId));
  if (!row || row.botId !== botId) throw new ValidationError(`chat_config_id inválido para este bot: ${chatConfigId}`);
}

export async function createTestCase(botId: string, input: TestCaseInput) {
  validateInput(input);
  await assertChatConfigBelongsToBot(botId, input.chatConfigId);

  const db = getDb();
  const [bot] = await db.select().from(bots).where(eq(bots.id, botId));
  if (!bot) throw new NotFoundError(`Bot no encontrado: ${botId}`);

  const id = crypto.randomUUID();
  await db.insert(testCases).values({
    id,
    botId,
    chatConfigId: input.chatConfigId,
    slug: input.slug.trim(),
    title: input.title.trim(),
    description: input.description?.trim() || null,
    turns: input.turns,
    checks: input.checks,
    position: input.position ?? 0,
  });
  return getTestCaseDto(botId, id);
}

export async function updateTestCase(botId: string, caseId: string, input: TestCaseInput) {
  validateInput(input);
  await assertChatConfigBelongsToBot(botId, input.chatConfigId);
  await getTestCaseRow(botId, caseId); // 404 si no existe / no es de este bot

  const db = getDb();
  await db
    .update(testCases)
    .set({
      chatConfigId: input.chatConfigId,
      slug: input.slug.trim(),
      title: input.title.trim(),
      description: input.description?.trim() || null,
      turns: input.turns,
      checks: input.checks,
      position: input.position ?? 0,
      updatedAt: new Date(),
    })
    .where(eq(testCases.id, caseId));
  return getTestCaseDto(botId, caseId);
}

export async function deleteTestCase(botId: string, caseId: string): Promise<void> {
  await getTestCaseRow(botId, caseId);
  const db = getDb();
  await db.delete(testCases).where(eq(testCases.id, caseId));
}

// ─── Resultados de corridas ─────────────────────────────────────────────

type TestRunRow = typeof testRuns.$inferSelect;

function toRunDto(row: TestRunRow) {
  return {
    id: row.id,
    bot_id: row.botId,
    suite_run_id: row.suiteRunId,
    test_case_id: row.testCaseId,
    test_case_title: row.testCaseTitle,
    target: row.target,
    status: row.status,
    turns: row.turns,
    check_results: row.checkResults,
    error_message: row.errorMessage,
    started_at: row.startedAt,
    finished_at: row.finishedAt,
  };
}

// Detalle completo (incluye `steps` + `flow_snapshot`, pesados -- solo para
// la vista "Ver" de UNA corrida puntual, nunca para el listado).
function toRunDetailDto(row: TestRunRow) {
  return { ...toRunDto(row), steps: row.steps, flow_snapshot: row.flowSnapshot, diagram_image: row.diagramImage };
}

export async function getTestRun(botId: string, runId: string) {
  const db = getDb();
  const [row] = await db.select().from(testRuns).where(and(eq(testRuns.id, runId), eq(testRuns.botId, botId)));
  if (!row) throw new NotFoundError(`Corrida no encontrada: ${runId}`);
  return toRunDetailDto(row);
}

// Corrida más reciente de un caso puntual -- usada por el ícono "Ver" en la
// fila del caso (antes de tener ninguna corrida seleccionada explícitamente).
export async function getLatestTestRunForCase(botId: string, testCaseId: string) {
  const db = getDb();
  const [row] = await db
    .select()
    .from(testRuns)
    .where(and(eq(testRuns.botId, botId), eq(testRuns.testCaseId, testCaseId)))
    .orderBy(desc(testRuns.startedAt))
    .limit(1);
  return row ? toRunDetailDto(row) : null;
}
