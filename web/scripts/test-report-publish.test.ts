import { test } from "node:test";
import assert from "node:assert/strict";
import { buildSummary } from "../lib/business/test-report-publish";

test("buildSummary cuenta passed/failed sobre el total", () => {
  const summary = buildSummary([{ status: "passed" }, { status: "passed" }, { status: "error" }, { status: "review" }]);
  assert.deepEqual(summary, { total: 4, passed: 2, failed: 2 });
});

test("buildSummary con lista vacía da todo en cero", () => {
  assert.deepEqual(buildSummary([]), { total: 0, passed: 0, failed: 0 });
});
