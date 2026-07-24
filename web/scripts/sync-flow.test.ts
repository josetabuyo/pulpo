import { test } from "node:test";
import assert from "node:assert/strict";
import { parseDirection } from "./sync-flow";

test("parseDirection acepta pull y push", () => {
  assert.equal(parseDirection("pull"), "pull");
  assert.equal(parseDirection("push"), "push");
});

test("parseDirection rechaza cualquier otro valor", () => {
  assert.throws(() => parseDirection("sideways"), /--direction inválido/);
  assert.throws(() => parseDirection(undefined), /--direction inválido/);
});
