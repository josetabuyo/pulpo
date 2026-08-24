import { test } from "node:test";
import assert from "node:assert/strict";
import { bucketRunRows, type RunStatsRow } from "../lib/business/run-stats";

const SINCE = new Date("2026-08-24T12:00:00Z");
const NOW = new Date("2026-08-24T12:10:00Z"); // 10 min de ventana

function row(startedAt: string, status: string): RunStatsRow {
  return { startedAt: new Date(startedAt), status };
}

test("bucketea completed/handed_off como success, error como error, el resto como pending", () => {
  const rows: RunStatsRow[] = [
    row("2026-08-24T12:00:30Z", "completed"),
    row("2026-08-24T12:01:00Z", "handed_off"),
    row("2026-08-24T12:02:00Z", "error"),
    row("2026-08-24T12:03:00Z", "running"),
    row("2026-08-24T12:04:00Z", "waiting_gate"),
  ];
  const buckets = bucketRunRows(rows, SINCE, 1, NOW);
  assert.equal(buckets[0].success, 1); // 12:00:30
  assert.equal(buckets[1].success, 1); // 12:01:00
  assert.equal(buckets[2].error, 1); // 12:02:00
  assert.equal(buckets[3].pending, 1); // 12:03:00 running
  assert.equal(buckets[4].pending, 1); // 12:04:00 waiting_gate
});

test("genera buckets vacíos cubriendo toda la ventana aunque no haya filas", () => {
  const buckets = bucketRunRows([], SINCE, 1, NOW);
  assert.equal(buckets.length, 10); // 10 min / 1 min por bucket
  for (const b of buckets) {
    assert.deepEqual(b, { startedAt: b.startedAt, success: 0, error: 0, pending: 0 });
  }
});

test("descarta filas sin startedAt", () => {
  const rows: RunStatsRow[] = [{ startedAt: null, status: "completed" }];
  const buckets = bucketRunRows(rows, SINCE, 1, NOW);
  const total = buckets.reduce((acc, b) => acc + b.success + b.error + b.pending, 0);
  assert.equal(total, 0);
});

test("descarta filas fuera de rango (antes de since o después de now)", () => {
  const rows: RunStatsRow[] = [
    row("2026-08-24T11:59:00Z", "completed"), // antes de since
    row("2026-08-24T12:30:00Z", "completed"), // después de la ventana
  ];
  const buckets = bucketRunRows(rows, SINCE, 1, NOW);
  const total = buckets.reduce((acc, b) => acc + b.success + b.error + b.pending, 0);
  assert.equal(total, 0);
});

test("bucketMinutes mayor agrupa varias filas en el mismo bucket", () => {
  const rows: RunStatsRow[] = [
    row("2026-08-24T12:01:00Z", "completed"),
    row("2026-08-24T12:04:00Z", "completed"),
    row("2026-08-24T12:06:00Z", "error"),
  ];
  const buckets = bucketRunRows(rows, SINCE, 5, NOW);
  assert.equal(buckets.length, 2); // 10 min / 5 min por bucket
  assert.equal(buckets[0].success, 2);
  assert.equal(buckets[1].error, 1);
});

test("ventana de 0ms produce al menos un bucket (piso de bucketCount)", () => {
  const buckets = bucketRunRows([], SINCE, 1, SINCE);
  assert.equal(buckets.length, 1);
});
