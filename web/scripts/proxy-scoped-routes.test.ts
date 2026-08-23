import { test } from "node:test";
import assert from "node:assert/strict";
import { SCOPED_BOT_ROUTES, SELF_VALIDATING_ROUTES } from "../proxy";

// Replica la lógica de matching de proxy.ts (no exportada como función):
// mismo método + regex ancla, primer grupo capturado es el botId.
function scopedMatch(method: string, pathname: string): string | null {
  for (const { method: m, re } of SCOPED_BOT_ROUTES) {
    if (m !== method) continue;
    const match = re.exec(pathname);
    if (match) return match[1];
  }
  return null;
}

function isSelfValidating(method: string, pathname: string): boolean {
  return SELF_VALIDATING_ROUTES.some(({ method: m, re }) => m === method && re.test(pathname));
}

// Tab "Test" (2026-08-23, paridad admin/cliente -- ver BotCard.jsx): un
// scoped con el bot en su allowlist puede llegar a estas rutas vía proxy
// (el handler hace su propio assertBotAccess encima, defense-in-depth).
test("scoped: rutas de test-cases/test-runs/api-key matchean con botId capturado", () => {
  assert.equal(scopedMatch("GET", "/api/bots/luganense/test-cases"), "luganense");
  assert.equal(scopedMatch("POST", "/api/bots/luganense/test-cases"), "luganense");
  assert.equal(scopedMatch("GET", "/api/bots/luganense/test-cases/case-1"), "luganense");
  assert.equal(scopedMatch("PUT", "/api/bots/luganense/test-cases/case-1"), "luganense");
  assert.equal(scopedMatch("DELETE", "/api/bots/luganense/test-cases/case-1"), "luganense");
  assert.equal(scopedMatch("GET", "/api/bots/luganense/test-cases/case-1/latest-run"), "luganense");
  assert.equal(scopedMatch("POST", "/api/bots/luganense/test-cases/case-1/run"), "luganense");
  assert.equal(scopedMatch("POST", "/api/bots/luganense/test-runs"), "luganense");
  assert.equal(scopedMatch("GET", "/api/bots/luganense/test-runs/run-1"), "luganense");
  assert.equal(scopedMatch("POST", "/api/bots/luganense/api-key"), "luganense");
});

test("scoped: GET /api/runs/bots/{botId} sigue matcheando (tab Ejecuciones, ya existía)", () => {
  assert.equal(scopedMatch("GET", "/api/runs/bots/luganense"), "luganense");
});

test("scoped: método equivocado no matchea (GET-only vs PUT/DELETE separados)", () => {
  assert.equal(scopedMatch("PATCH", "/api/bots/luganense/test-cases"), null);
  assert.equal(scopedMatch("DELETE", "/api/bots/luganense/test-runs"), null);
});

test("scoped: /api/bots/{botId}/users NO matchea ninguna ruta de test (admin-only, sin cambios)", () => {
  assert.equal(scopedMatch("GET", "/api/bots/luganense/users"), null);
});

// GET /api/runs/{runId} y GET /api/runs/stats: no tienen botId en el path,
// así que dependen de SELF_VALIDATING_ROUTES en el proxy + assertBotAccess
// real dentro del handler (ver app/api/runs/[runId]/route.ts y
// app/api/runs/stats/route.ts).
test("self-validating: GET /api/runs/{runId} y GET /api/runs/stats pasan el gate del proxy con solo sesión", () => {
  assert.equal(isSelfValidating("GET", "/api/runs/abc123"), true);
  assert.equal(isSelfValidating("GET", "/api/runs/stats"), true);
});

test("self-validating: no se cuela nada fuera de esas dos rutas puntuales", () => {
  assert.equal(isSelfValidating("GET", "/api/runs/bots/luganense"), false); // esa va por SCOPED_BOT_ROUTES
  assert.equal(isSelfValidating("DELETE", "/api/runs/abc123"), false); // solo GET
  assert.equal(isSelfValidating("GET", "/api/runs"), false); // listado global, admin-only
});
