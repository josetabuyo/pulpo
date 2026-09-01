import { test } from "node:test";
import assert from "node:assert/strict";
import { guessMimeFromUrl, parseJsonResponse } from "../lib/nodes/document-vision";
import { VISION_CASCADE } from "../lib/nodes/llm-client";

test("guessMimeFromUrl reconoce extensiones de imagen comunes", () => {
  assert.equal(guessMimeFromUrl("https://x.com/a/b.png"), "image/png");
  assert.equal(guessMimeFromUrl("https://x.com/a/b.jpg"), "image/jpeg");
  assert.equal(guessMimeFromUrl("https://x.com/a/b.JPEG"), "image/jpeg");
  assert.equal(guessMimeFromUrl("https://x.com/a/b.webp?x=1"), "image/webp");
});

test("guessMimeFromUrl cae a image/png si no reconoce la extensión", () => {
  assert.equal(guessMimeFromUrl("https://x.com/a/b"), "image/png");
  assert.equal(guessMimeFromUrl("https://x.com/a/b.pdf"), "image/png");
});

test("parseJsonResponse parsea JSON limpio", () => {
  const result = parseJsonResponse('{"proveedor":"ACME","importe_total":"100"}');
  assert.deepEqual(result, { proveedor: "ACME", importe_total: "100" });
});

// Bug real 2026-09-01: NVIDIA a veces devuelve el JSON envuelto en un fence
// ```json ... ``` a pesar de la instrucción de "sin bloques de código" --
// ver document-vision.ts JSON_INSTRUCTION.
test("parseJsonResponse tolera un fence ```json alrededor del objeto", () => {
  const result = parseJsonResponse('```json\n{"numero":"123"}\n```');
  assert.deepEqual(result, { numero: "123" });
});

test("parseJsonResponse devuelve _parse_error en vez de perder el texto crudo", () => {
  const result = parseJsonResponse("¡Hola! No puedo leer eso, ¡saludos!");
  assert.equal(result._parse_error, true);
  assert.equal(result._raw, "¡Hola! No puedo leer eso, ¡saludos!");
});

test("parseJsonResponse rechaza arrays (espera un objeto, no una lista)", () => {
  const result = parseJsonResponse("[1,2,3]");
  assert.equal(result._parse_error, true);
});

// Guardrail de regresión: Groq no tiene ningún modelo con visión en su
// catálogo (verificado con GET /v1/models, 2026-09-01) -- si alguien lo
// vuelve a agregar sin chequear el catálogo primero, el nodo document_vision
// va a fallar en ese provider en producción. Ver comentario en llm-client.ts.
test("VISION_CASCADE no incluye Groq", () => {
  assert.ok(
    VISION_CASCADE.every((entry) => entry.provider !== "groq"),
    "Groq no tiene modelos con visión -- no debería estar en la cascada de document_vision",
  );
  assert.ok(VISION_CASCADE.length > 0, "la cascada de visión no puede estar vacía");
});
