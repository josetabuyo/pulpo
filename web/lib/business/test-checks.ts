// Tipos + evaluador de validaciones ("checks") para la suite de tests e2e
// configurable desde la UI. Puerto directo de `_StepsAnalysisMixin` +
// `_c`/`_log`/`_ran_all`/`_infra_checks`/`_no_separator_leak` en
// tests/e2e/helpers.py y tests/e2e/luganense/scenarios_orquestador_vendedor_0019d8f2.py
// (Python) -- misma semántica, mismos valores default (`occurrence=-1`),
// evaluados acá sobre el mismo shape de step que devuelve `getOwnRunSteps`
// (lib/business/chats.ts): node_id/node_type/status/output_state/branch_taken.
//
// Deliberadamente SIN escape hatch de expresión custom (decisión del
// usuario) -- solo estos tipos, elegidos en la UI vía dropdowns.

export type CheckKind = "assert" | "log";

export interface RanNodeCheck {
  type: "ran_node";
  nodeId: string;
  status?: string; // default "ok"
  occurrence?: number; // default -1
  kind: CheckKind;
  label: string;
}

export interface BranchTakenCheck {
  type: "branch_taken";
  nodeId: string;
  expected?: string;
  occurrence?: number;
  kind: CheckKind;
  label: string;
}

export interface StateFieldCheck {
  type: "state_field";
  nodeId: string;
  key: string;
  operator: "equals" | "contains" | "not_empty";
  value?: string;
  occurrence?: number;
  kind: CheckKind;
  label: string;
}

export interface MinFetchResultsCheck {
  type: "min_fetch_results";
  nodeId: string;
  field: string;
  min: number;
  kind: CheckKind;
  label: string;
}

export interface ReplyNotEmptyCheck {
  type: "reply_not_empty";
  kind: CheckKind;
  label: string;
}

export interface NoUnresolvedTemplatesCheck {
  type: "no_unresolved_templates";
  kind: CheckKind;
  label: string;
}

export interface NoFetchErrorsCheck {
  type: "no_fetch_errors";
  kind: CheckKind;
  label: string;
}

export interface NoLlmErrorsCheck {
  type: "no_llm_errors";
  kind: CheckKind;
  label: string;
}

export interface NoNodeErrorsCheck {
  type: "no_node_errors";
  kind: CheckKind;
  label: string;
}

export interface ReachedEndConversationCheck {
  type: "reached_end_conversation";
  kind: CheckKind;
  label: string;
}

export interface NoSeparatorLeakCheck {
  type: "no_separator_leak";
  separator?: string; // default "|||"
  kind: CheckKind;
  label: string;
}

export type CheckSpec =
  | RanNodeCheck
  | BranchTakenCheck
  | StateFieldCheck
  | MinFetchResultsCheck
  | ReplyNotEmptyCheck
  | NoUnresolvedTemplatesCheck
  | NoFetchErrorsCheck
  | NoLlmErrorsCheck
  | NoNodeErrorsCheck
  | ReachedEndConversationCheck
  | NoSeparatorLeakCheck;

export const CHECK_TYPES: { type: CheckSpec["type"]; label: string; needsNode: boolean }[] = [
  { type: "ran_node", label: "El nodo corrió", needsNode: true },
  { type: "branch_taken", label: "Rama tomada en un nodo condición/router", needsNode: true },
  { type: "state_field", label: "Campo del estado (igual / contiene / no vacío)", needsNode: true },
  { type: "min_fetch_results", label: "Cantidad mínima de resultados de un fetch", needsNode: true },
  { type: "reply_not_empty", label: "El bot respondió (no vacío)", needsNode: false },
  { type: "no_unresolved_templates", label: "Sin placeholders {{...}} sin resolver", needsNode: false },
  { type: "no_fetch_errors", label: "Sin fetch HTTP fallidos", needsNode: false },
  { type: "no_llm_errors", label: "Sin contenido vacío persistente de un LLM", needsNode: false },
  { type: "no_node_errors", label: "Ningún nodo crasheó", needsNode: false },
  { type: "reached_end_conversation", label: "Llegó a un end_conversation real", needsNode: false },
  { type: "no_separator_leak", label: "Sin fuga del separador técnico \"|||\"", needsNode: false },
];

export interface StepDto {
  id?: number;
  node_id: string;
  node_type?: string;
  started_at?: string | Date | null;
  ended_at?: string | Date | null;
  input_state?: Record<string, unknown> | null;
  output_state?: Record<string, unknown> | null;
  branch_taken?: string | null;
  status?: string | null;
  error_message?: string | null;
}

export interface TurnDto {
  role: "user" | "bot";
  text: string | null;
}

export interface CheckResult {
  label: string;
  kind: CheckKind;
  passed: boolean;
  detail: string;
}

const UNRESOLVED_TEMPLATE_RE = /\{\{.*?\}\}/;

export function hasUnresolvedTemplates(...texts: (string | null | undefined)[]): boolean {
  return texts.some((t) => t && UNRESOLVED_TEMPLATE_RE.test(t));
}

// `output_state` tal como lo persiste `logFlowStep` (lib/flow/steps.ts) es un
// snapshot COMPLETO de `FlowState` (lib/nodes/state.ts) -- los campos que
// escribe cada nodo (necesidad, comercio_luganense, _fetch_errors, etc.) van
// adentro de `state.data`, no sueltos en la raíz (botId/canal/message sí
// están sueltos, pero esos no son campos de nodo). `getOwnRunSteps`
// (lib/business/chats.ts) devuelve ese mismo shape sin aplanar. Este helper
// centraliza el unwrap para no repetirlo en cada accessor de abajo.
function nodeData(step: StepDto): Record<string, unknown> {
  const raw = step.output_state as (Record<string, unknown> & { data?: Record<string, unknown> }) | null | undefined;
  if (!raw) return {};
  return raw.data && typeof raw.data === "object" ? (raw.data as Record<string, unknown>) : raw;
}

// Acumulador de steps de todos los turnos de una conversación + accessors de
// validación -- puerto de `_StepsAnalysisMixin` (tests/e2e/helpers.py).
export class ConversationSteps {
  allSteps: StepDto[] = [];

  addTurnSteps(steps: StepDto[]) {
    this.allSteps.push(...steps);
  }

  step(nodeId: string, occurrence = -1): StepDto | null {
    const matches = this.allSteps.filter((s) => s.node_id === nodeId);
    if (matches.length === 0) return null;
    const idx = occurrence < 0 ? matches.length + occurrence : occurrence;
    return matches[idx] ?? null;
  }

  ranNode(nodeId: string, status = "ok", occurrence = -1): boolean {
    const s = this.step(nodeId, occurrence);
    return Boolean(s) && s?.status === status;
  }

  stateField(nodeId: string, key: string, occurrence = -1): unknown {
    const s = this.step(nodeId, occurrence);
    if (!s) return undefined;
    return nodeData(s)[key];
  }

  branchTaken(nodeId: string, occurrence = -1): string | null {
    const s = this.step(nodeId, occurrence);
    return s?.branch_taken ?? null;
  }

  reachedEndConversation(lastTurnSteps: StepDto[]): boolean {
    return lastTurnSteps.some((s) => s.node_type === "end_conversation");
  }

  // Excluye "conversation" (ya cubierto por hasUnresolvedTemplates sobre
  // replies) y claves que terminan en "_prompt" (copia cruda de un parámetro
  // de NodoFlow que interpolate() resuelve recién en la 2ª pasada -- no es
  // un bug, ver docstring largo de state_unresolved_templates en helpers.py).
  stateUnresolvedTemplates(): { nodeId: string; key: string; value: string }[] {
    const found: { nodeId: string; key: string; value: string }[] = [];
    for (const step of this.allSteps) {
      const output = nodeData(step);
      for (const [key, value] of Object.entries(output)) {
        if (key === "conversation") continue;
        if (key.endsWith("_prompt")) continue;
        if (typeof value === "string" && UNRESOLVED_TEMPLATE_RE.test(value)) {
          found.push({ nodeId: step.node_id, key, value });
        }
      }
    }
    return found;
  }

  private lastListField(key: string): unknown[] {
    for (let i = this.allSteps.length - 1; i >= 0; i--) {
      const output = nodeData(this.allSteps[i]);
      if (key in output) {
        const v = output[key];
        return Array.isArray(v) ? v : [];
      }
    }
    return [];
  }

  fetchErrors(): unknown[] {
    return this.lastListField("_fetch_errors");
  }

  llmErrors(): unknown[] {
    return this.lastListField("_llm_errors");
  }

  nodeErrors(): unknown[] {
    return this.lastListField("_node_errors");
  }

  crashedNodes(): string[] {
    return this.allSteps.filter((s) => s.status === "error").map((s) => s.node_id);
  }
}

export interface CheckEvalContext {
  conv: ConversationSteps;
  lastTurnSteps: StepDto[];
  turns: TurnDto[];
  lastReply: string | null;
}

function label(spec: CheckSpec, fallback: string): string {
  return spec.label?.trim() || fallback;
}

export function evaluateCheck(spec: CheckSpec, ctx: CheckEvalContext): CheckResult {
  const kind = spec.kind ?? "assert";
  const mk = (lbl: string, passed: boolean, detail = ""): CheckResult => ({
    label: lbl,
    kind,
    // Un check "log" nunca hace fallar el caso -- siempre passed=true,
    // mismo criterio que `_log()` en Python.
    passed: kind === "log" ? true : passed,
    detail,
  });

  switch (spec.type) {
    case "ran_node": {
      const occurrence = spec.occurrence ?? -1;
      const status = spec.status ?? "ok";
      const ok = ctx.conv.ranNode(spec.nodeId, status, occurrence);
      const s = ctx.conv.step(spec.nodeId, occurrence);
      return mk(
        label(spec, `El nodo ${spec.nodeId} corrió (status=${status})`),
        ok,
        ok ? "" : `nodo no corrió con ese status -- step encontrado: ${JSON.stringify(s)}`,
      );
    }
    case "branch_taken": {
      const occurrence = spec.occurrence ?? -1;
      const branch = ctx.conv.branchTaken(spec.nodeId, occurrence);
      const ok = spec.expected === undefined ? branch !== null : branch === spec.expected;
      return mk(
        label(spec, `Rama tomada en ${spec.nodeId}${spec.expected ? ` == "${spec.expected}"` : ""}`),
        ok,
        ok ? "" : `branch_taken=${JSON.stringify(branch)}`,
      );
    }
    case "state_field": {
      const occurrence = spec.occurrence ?? -1;
      const value = ctx.conv.stateField(spec.nodeId, spec.key, occurrence);
      let ok: boolean;
      if (spec.operator === "not_empty") {
        ok = value !== undefined && value !== null && value !== "";
      } else if (spec.operator === "equals") {
        ok = String(value ?? "") === (spec.value ?? "");
      } else {
        ok = typeof value === "string" && value.includes(spec.value ?? "");
      }
      return mk(
        label(spec, `${spec.nodeId}.${spec.key} ${spec.operator} ${spec.value ?? ""}`.trim()),
        ok,
        ok ? "" : `valor real: ${JSON.stringify(value)}`,
      );
    }
    case "min_fetch_results": {
      const raw = ctx.conv.stateField(spec.nodeId, spec.field);
      const responses = Array.isArray(raw) ? raw : [raw];
      let total = 0;
      for (const r of responses) {
        if (!r) continue;
        try {
          const parsed = typeof r === "string" ? JSON.parse(r) : r;
          total += (parsed?.results ?? []).length;
        } catch {
          // no-op -- respuesta no era JSON parseable, no suma
        }
      }
      const ok = total >= spec.min;
      return mk(
        label(spec, `${spec.nodeId}.${spec.field} tiene al menos ${spec.min} resultado(s)`),
        ok,
        ok ? "" : `total_results=${total}`,
      );
    }
    case "reply_not_empty": {
      const ok = Boolean(ctx.lastReply);
      return mk(label(spec, "El bot respondió en el último turno"), ok, ok ? "" : JSON.stringify(ctx.lastReply));
    }
    case "no_unresolved_templates": {
      const replyBroken = hasUnresolvedTemplates(ctx.lastReply);
      const stateBroken = ctx.conv.stateUnresolvedTemplates();
      const ok = !replyBroken && stateBroken.length === 0;
      return mk(
        label(spec, "Sin placeholders {{...}} sin resolver (reply ni estado)"),
        ok,
        ok ? "" : JSON.stringify({ replyBroken, stateBroken }),
      );
    }
    case "no_fetch_errors": {
      const errors = ctx.conv.fetchErrors();
      return mk(label(spec, "Sin fetch HTTP fallidos en toda la conversación"), errors.length === 0, errors.length ? JSON.stringify(errors) : "");
    }
    case "no_llm_errors": {
      const errors = ctx.conv.llmErrors();
      return mk(label(spec, "Sin contenido vacío persistente de un LLM"), errors.length === 0, errors.length ? JSON.stringify(errors) : "");
    }
    case "no_node_errors": {
      const errors = ctx.conv.nodeErrors();
      const crashed = ctx.conv.crashedNodes();
      const ok = errors.length === 0 && crashed.length === 0;
      return mk(label(spec, "Ningún nodo crasheó"), ok, ok ? "" : JSON.stringify({ errors, crashed }));
    }
    case "reached_end_conversation": {
      const ok = ctx.conv.reachedEndConversation(ctx.lastTurnSteps);
      return mk(label(spec, "La conversación llegó a un end_conversation real"), ok);
    }
    case "no_separator_leak": {
      const sep = spec.separator ?? "|||";
      const leaked = ctx.turns.filter((t) => t.role === "bot" && (t.text ?? "").includes(sep));
      return mk(
        label(spec, `Ningún reply filtró el separador técnico "${sep}"`),
        leaked.length === 0,
        leaked.length ? JSON.stringify(leaked.map((t) => t.text)) : "",
      );
    }
  }
}
