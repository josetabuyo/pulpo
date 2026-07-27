import { test } from "node:test";
import assert from "node:assert/strict";
import { computeRunRetentionDeleteIds, type RunRetentionRow } from "../lib/business/test-runner";

const DAY = 24 * 60 * 60 * 1000;
const NOW = new Date("2026-07-27T18:00:00Z");

function row(id: string, suiteRunId: string, daysAgo: number, hourOffsetMs = 0): RunRetentionRow {
  return { id, suiteRunId, startedAt: new Date(NOW.getTime() - daysAgo * DAY + hourOffsetMs) };
}

test("hoy: conserva las últimas 10 ejecuciones, borra el resto", () => {
  const rows: RunRetentionRow[] = [];
  // 12 ejecuciones distintas hoy, cada una con 1 fila, ordenadas de más vieja a más nueva.
  for (let i = 0; i < 12; i++) {
    rows.push(row(`r${i}`, `suite${i}`, 0, i * 1000)); // más alto i = más reciente
  }
  const toDelete = computeRunRetentionDeleteIds(rows, NOW);
  // Se borran las 2 más viejas (suite0, suite1); se conservan suite2..suite11.
  assert.deepEqual(new Set(toDelete), new Set(["r0", "r1"]));
});

test("día pasado: comprime a la última ejecución del día", () => {
  const rows: RunRetentionRow[] = [
    row("a1", "suiteA", 1, 0),
    row("a2", "suiteA", 1, 1000), // misma suite, otro caso del mismo run
    row("b1", "suiteB", 1, 2000), // más reciente que suiteA -- se conserva
  ];
  const toDelete = computeRunRetentionDeleteIds(rows, NOW);
  assert.deepEqual(new Set(toDelete), new Set(["a1", "a2"]));
});

test("día fuera de la ventana de 30 días: se borra entero, incluida la comprimida", () => {
  const rows: RunRetentionRow[] = [row("old1", "suiteOld", 31, 0)];
  const toDelete = computeRunRetentionDeleteIds(rows, NOW);
  assert.deepEqual(new Set(toDelete), new Set(["old1"]));
});

test("día exactamente en el borde de 30 días se conserva (comprimido)", () => {
  const rows: RunRetentionRow[] = [
    row("edgeA", "suiteEdgeA", 29, 0),
    row("edgeB", "suiteEdgeB", 29, 1000),
  ];
  const toDelete = computeRunRetentionDeleteIds(rows, NOW);
  assert.deepEqual(new Set(toDelete), new Set(["edgeA"]));
});

test("nada que borrar cuando todo entra dentro de la política", () => {
  const rows: RunRetentionRow[] = [
    row("t1", "suiteToday", 0, 0),
    row("y1", "suiteYesterday", 1, 0),
  ];
  assert.deepEqual(computeRunRetentionDeleteIds(rows, NOW), []);
});

test("múltiples días pasados: cada uno se comprime independientemente", () => {
  const rows: RunRetentionRow[] = [
    row("d2a", "suiteD2A", 2, 0),
    row("d2b", "suiteD2B", 2, 1000),
    row("d3a", "suiteD3A", 3, 0),
  ];
  const toDelete = computeRunRetentionDeleteIds(rows, NOW);
  assert.deepEqual(new Set(toDelete), new Set(["d2a"]));
});
