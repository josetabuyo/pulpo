import { test } from "node:test";
import assert from "node:assert/strict";
import { parseCaseIds } from "../cli/main";

test("parseCaseIds sin --cases devuelve undefined (correr todos)", () => {
  assert.equal(parseCaseIds(undefined), undefined);
  assert.equal(parseCaseIds(true), undefined); // --cases sin valor (flag booleano)
});

test("parseCaseIds separa por coma y descarta vacíos", () => {
  assert.deepEqual(parseCaseIds("a,b,c"), ["a", "b", "c"]);
  assert.deepEqual(parseCaseIds(" a , b ,,c "), ["a", "b", "c"]);
});

test("parseCaseIds con string vacío/solo comas devuelve undefined", () => {
  assert.equal(parseCaseIds(""), undefined);
  assert.equal(parseCaseIds(",,,"), undefined);
});
