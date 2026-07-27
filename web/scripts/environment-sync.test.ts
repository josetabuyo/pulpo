import { test } from "node:test";
import assert from "node:assert/strict";
import { parseSyncDirection } from "../lib/business/environment-sync";

test("parseSyncDirection acepta pull y push", () => {
  assert.equal(parseSyncDirection("pull"), "pull");
  assert.equal(parseSyncDirection("push"), "push");
});

test("parseSyncDirection rechaza cualquier otro valor", () => {
  assert.throws(() => parseSyncDirection("sideways"), /direction inválido/);
  assert.throws(() => parseSyncDirection(undefined), /direction inválido/);
  assert.throws(() => parseSyncDirection(null), /direction inválido/);
});
