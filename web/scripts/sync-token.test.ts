import { test } from "node:test";
import assert from "node:assert/strict";
import { isSyncTokenRequest } from "../lib/auth/sync-token";

function reqWithHeader(value: string | null): Request {
  const headers = new Headers();
  if (value !== null) headers.set("x-pulpo-sync-token", value);
  return new Request("http://localhost/api/flows/bots/x/y", { headers });
}

test("isSyncTokenRequest false cuando PULPO_SYNC_TOKEN no está seteado", () => {
  delete process.env.PULPO_SYNC_TOKEN;
  assert.equal(isSyncTokenRequest(reqWithHeader("cualquier-cosa")), false);
});

test("isSyncTokenRequest false cuando el header no coincide", () => {
  process.env.PULPO_SYNC_TOKEN = "el-token-correcto";
  assert.equal(isSyncTokenRequest(reqWithHeader("otro-token")), false);
  assert.equal(isSyncTokenRequest(reqWithHeader(null)), false);
  delete process.env.PULPO_SYNC_TOKEN;
});

test("isSyncTokenRequest true cuando el header coincide exacto", () => {
  process.env.PULPO_SYNC_TOKEN = "el-token-correcto";
  assert.equal(isSyncTokenRequest(reqWithHeader("el-token-correcto")), true);
  delete process.env.PULPO_SYNC_TOKEN;
});
