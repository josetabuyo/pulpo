import { test } from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import {
  renderTemplate,
  renderDeep,
  toPublicDirectoryDto,
  signItemToken,
  verifyItemToken,
  validateFields,
  UnresolvedTemplateError,
} from "../lib/business/chat-directory";
import {
  validateDirectoryConfig,
  isPaginatedSource,
  type DirectoryConfig,
  type DirectorySection,
} from "../lib/business/chat-directory-types";
import { ValidationError } from "../lib/business/bots";

process.env.JWT_SECRET_KEY ||= "test-secret-for-chat-directory";

function sampleConfig(): DirectoryConfig {
  return validateDirectoryConfig({
    version: 1,
    enabled: true,
    title: "Directorio",
    sections: [
      {
        id: "comercios",
        label: "Comercios",
        search_placeholder: "Buscar…",
        empty_query: "search",
        source: {
          method: "GET",
          url: "https://cliente.example.com/api/directorio/buscar?q={{q}}&tipo=comercios",
          headers: { Authorization: "Bearer {{env.TOKEN}}" },
          items_path: "results",
          item_map: { id: "id", title: "nombre", subtitle: "rubro", meta: "direccion" },
          limit: 30,
        },
        connect: {
          label: "Conectar",
          fields: [],
          confirm_text: "¿Conectarte con {{item.title}}?",
          success_text: "Listo, ya avisamos a {{item.title}}.",
          lead: {
            method: "POST",
            url: "https://cliente.example.com/api/actividad-comercial",
            success_codes: [200, 201],
            body: {
              tipo: "comercio_confirmado",
              payload: { comercio: "{{item.title}}" },
              contact_id: "{{contact.id}}",
              contact_channel: "{{contact.channel}}",
            },
          },
        },
      },
      {
        id: "servicios",
        label: "Servicios",
        source: {
          method: "GET",
          url: "https://cliente.example.com/api/directorio/buscar?q={{q}}&tipo=servicios",
          items_path: "results",
          item_map: { id: "id", title: "nombre", subtitle: "categoria" },
        },
        connect: {
          label: "Conectar",
          fields: [{ name: "direccion", label: "Dirección", type: "text", required: true }],
          lead: {
            method: "POST",
            url: "https://cliente.example.com/api/actividad-comercial",
            success_codes: [201],
            body: {
              tipo: "pedido_servicio_concretado",
              payload: { profesional: "{{item.title}}", direccion: "{{fields.direccion}}" },
            },
          },
        },
      },
    ],
  });
}

// ─── renderTemplate / renderDeep ────────────────────────────────────────

test("renderTemplate resuelve {{q}} con URL-encoding", () => {
  const url = renderTemplate("https://x/buscar?q={{q}}&tipo=comercios", { q: "café con leche" }, { urlEncode: true });
  assert.equal(url, "https://x/buscar?q=caf%C3%A9%20con%20leche&tipo=comercios");
});

test("renderTemplate resuelve namespaces item/fields/contact/chat/env", () => {
  const ctx = {
    item: { title: "Alberto", raw: { nombre: "Alberto" } },
    fields: { direccion: "Av. Siempreviva 742" },
    contact: { id: "anon:123", channel: "chat" },
    chat: { bot_id: "b1", id: "c1", title: "Mi chat" },
    env: { TOKEN: "secreto" },
  };
  assert.equal(renderTemplate("{{item.title}}", ctx), "Alberto");
  assert.equal(renderTemplate("{{fields.direccion}}", ctx), "Av. Siempreviva 742");
  assert.equal(renderTemplate("{{contact.id}}/{{contact.channel}}", ctx), "anon:123/chat");
  assert.equal(renderTemplate("{{chat.title}}", ctx), "Mi chat");
  assert.equal(renderTemplate("Bearer {{env.TOKEN}}", ctx), "Bearer secreto");
});

test("renderTemplate no-strict deja {{...}} sin resolver intacto", () => {
  const result = renderTemplate("valor: {{item.inexistente}}", { item: { title: "x" } }, { strict: false });
  assert.equal(result, "valor: {{item.inexistente}}");
});

test("renderTemplate strict lanza UnresolvedTemplateError", () => {
  assert.throws(
    () => renderTemplate("{{item.inexistente}}", { item: { title: "x" } }, { strict: true }),
    UnresolvedTemplateError,
  );
});

test("renderDeep aplica renderTemplate recursivamente en objetos/arrays, strict propaga el error", () => {
  const ctx = { item: { title: "Alberto" }, fields: {}, contact: { id: "a", channel: "chat" } };
  const body = renderDeep(
    { tipo: "x", payload: { comercio: "{{item.title}}" }, tags: ["{{item.title}}", "fijo"] },
    ctx,
    { strict: true },
  );
  assert.deepEqual(body, { tipo: "x", payload: { comercio: "Alberto" }, tags: ["Alberto", "fijo"] });

  assert.throws(() => renderDeep({ payload: { comercio: "{{item.faltante}}" } }, ctx, { strict: true }), UnresolvedTemplateError);
});

// ─── toPublicDirectoryDto: no debe filtrar source/lead/env ──────────────

test("toPublicDirectoryDto nunca expone source.*/lead.*/headers/body/env", () => {
  const dto = toPublicDirectoryDto(sampleConfig());
  const serialized = JSON.stringify(dto);
  assert.ok(!serialized.includes("cliente.example.com"), "no debe incluir URLs upstream");
  assert.ok(!serialized.includes("Authorization"), "no debe incluir headers");
  assert.ok(!serialized.includes("Bearer"), "no debe incluir valores de headers");
  assert.ok(!serialized.includes("comercio_confirmado"), "no debe incluir el body del lead");
  assert.ok(!serialized.includes("success_codes"), "no debe incluir success_codes");

  assert.equal(dto.enabled, true);
  assert.equal(dto.sections.length, 2);
  const comercios = dto.sections.find((s) => s.id === "comercios")!;
  assert.equal(comercios.label, "Comercios");
  assert.equal(comercios.connect!.label, "Conectar");
  assert.deepEqual(comercios.connect!.fields, []);
  const servicios = dto.sections.find((s) => s.id === "servicios")!;
  assert.equal(servicios.connect!.fields[0].name, "direccion");
});

test("toPublicDirectoryDto con config null devuelve disabled sin secciones", () => {
  const dto = toPublicDirectoryDto(null);
  assert.equal(dto.enabled, false);
  assert.deepEqual(dto.sections, []);
});

// ─── item_token: HMAC firmado, TTL, forjado ──────────────────────────────

test("signItemToken / verifyItemToken: roundtrip válido", () => {
  const token = signItemToken("chat1", "comercios", "42");
  assert.equal(verifyItemToken(token, "chat1", "comercios", "42"), true);
});

test("verifyItemToken rechaza chatConfigId/sectionId/itemId distintos al firmado", () => {
  const token = signItemToken("chat1", "comercios", "42");
  assert.equal(verifyItemToken(token, "chat2", "comercios", "42"), false);
  assert.equal(verifyItemToken(token, "chat1", "servicios", "42"), false);
  assert.equal(verifyItemToken(token, "chat1", "comercios", "99"), false);
});

test("verifyItemToken rechaza un token forjado (firma no coincide)", () => {
  const token = signItemToken("chat1", "comercios", "42");
  const [payloadB64] = token.split(".");
  const forgedSig = crypto.createHmac("sha256", "otro-secreto-cualquiera").update(payloadB64).digest("base64url");
  assert.equal(verifyItemToken(`${payloadB64}.${forgedSig}`, "chat1", "comercios", "42"), false);
});

test("verifyItemToken rechaza tokens malformados", () => {
  assert.equal(verifyItemToken("", "chat1", "comercios", "42"), false);
  assert.equal(verifyItemToken("sin-punto", "chat1", "comercios", "42"), false);
  assert.equal(verifyItemToken("a.b.c", "chat1", "comercios", "42"), false);
});

test("verifyItemToken rechaza un token expirado", () => {
  // Reconstruye el mismo formato que signItemToken pero con `e` en el
  // pasado -- sin esto no hay forma de testear el TTL sin mockear Date.now.
  const secret = process.env.JWT_SECRET_KEY!;
  const payload = JSON.stringify({ c: "chat1", s: "comercios", i: "42", e: Date.now() - 1000 });
  const payloadB64 = Buffer.from(payload).toString("base64url");
  const sig = crypto.createHmac("sha256", secret).update(payloadB64).digest("base64url");
  const expiredToken = `${payloadB64}.${sig}`;
  assert.equal(verifyItemToken(expiredToken, "chat1", "comercios", "42"), false);
});

// ─── validateFields ──────────────────────────────────────────────────────

const servicioSection: DirectorySection = sampleConfig().sections.find((s) => s.id === "servicios")!;

test("validateFields exige campos required", () => {
  assert.throws(() => validateFields(servicioSection, {}), ValidationError);
  assert.throws(() => validateFields(servicioSection, { direccion: "  " }), ValidationError);
});

test("validateFields acepta y trimea un campo válido", () => {
  const out = validateFields(servicioSection, { direccion: "  Av. Siempreviva 742  " });
  assert.deepEqual(out, { direccion: "Av. Siempreviva 742" });
});

test("validateFields rechaza valores demasiado largos", () => {
  assert.throws(() => validateFields(servicioSection, { direccion: "x".repeat(501) }), ValidationError);
});

// ─── validateDirectoryConfig: shape + SSRF guard ─────────────────────────

test("validateDirectoryConfig rechaza URLs no-https (SSRF guard)", () => {
  assert.throws(
    () =>
      validateDirectoryConfig({
        version: 1,
        enabled: true,
        sections: [
          {
            id: "x",
            label: "X",
            source: {
              method: "GET",
              url: "http://cliente.example.com/buscar",
              items_path: "",
              item_map: { id: "id", title: "title" },
            },
            connect: {
              label: "Conectar",
              fields: [],
              lead: { method: "POST", url: "https://cliente.example.com/lead", success_codes: [200], body: {} },
            },
          },
        ],
      }),
    ValidationError,
  );
});

test("validateDirectoryConfig rechaza host loopback/privado", () => {
  assert.throws(
    () =>
      validateDirectoryConfig({
        version: 1,
        enabled: true,
        sections: [
          {
            id: "x",
            label: "X",
            source: { method: "GET", url: "https://localhost/buscar", items_path: "", item_map: { id: "id", title: "title" } },
            connect: {
              label: "Conectar",
              fields: [],
              lead: { method: "POST", url: "https://cliente.example.com/lead", success_codes: [200], body: {} },
            },
          },
        ],
      }),
    ValidationError,
  );
});

test("validateDirectoryConfig rechaza section ids duplicados", () => {
  const cfg = {
    version: 1,
    enabled: true,
    sections: [
      {
        id: "dup",
        label: "A",
        source: { method: "GET", url: "https://x.com/a", items_path: "", item_map: { id: "id", title: "title" } },
        connect: { label: "Conectar", fields: [], lead: { method: "POST", url: "https://x.com/lead", success_codes: [200], body: {} } },
      },
      {
        id: "dup",
        label: "B",
        source: { method: "GET", url: "https://x.com/b", items_path: "", item_map: { id: "id", title: "title" } },
        connect: { label: "Conectar", fields: [], lead: { method: "POST", url: "https://x.com/lead", success_codes: [200], body: {} } },
      },
    ],
  };
  assert.throws(() => validateDirectoryConfig(cfg), ValidationError);
});

test("validateDirectoryConfig acepta una config válida completa", () => {
  const cfg = sampleConfig();
  assert.equal(cfg.sections.length, 2);
});

// ─── mode: "detail" (ej. noticias) -- sin connect, con item_map.link ─────

function detailSectionRaw() {
  return {
    id: "noticias",
    label: "Noticias",
    mode: "detail",
    empty_query: "search",
    source: {
      method: "GET",
      url: "https://cliente.example.com/api/noticias?q={{q}}",
      items_path: "items",
      item_map: { id: "id", title: "titulo", description: "resumen", meta: "fecha", link: "url" },
    },
  };
}

test("validateDirectoryConfig acepta mode: detail sin connect", () => {
  const cfg = validateDirectoryConfig({
    version: 1,
    enabled: true,
    sections: [detailSectionRaw()],
  });
  const section = cfg.sections[0];
  assert.equal(section.mode, "detail");
  assert.equal(section.connect, undefined);
});

test("validateDirectoryConfig default mode es connect y exige connect", () => {
  assert.throws(
    () =>
      validateDirectoryConfig({
        version: 1,
        enabled: true,
        sections: [
          {
            id: "x",
            label: "X",
            source: { method: "GET", url: "https://x.com/a", items_path: "", item_map: { id: "id", title: "title" } },
          },
        ],
      }),
    ValidationError,
  );
});

test("validateDirectoryConfig rechaza mode inválido", () => {
  assert.throws(
    () =>
      validateDirectoryConfig({
        version: 1,
        enabled: true,
        sections: [{ ...detailSectionRaw(), mode: "borrar-todo" }],
      }),
    ValidationError,
  );
});

test("toPublicDirectoryDto propaga mode: detail sin connect", () => {
  const cfg = validateDirectoryConfig({ version: 1, enabled: true, sections: [detailSectionRaw()] });
  const dto = toPublicDirectoryDto(cfg);
  const noticias = dto.sections.find((s) => s.id === "noticias")!;
  assert.equal(noticias.mode, "detail");
  assert.equal(noticias.connect, undefined);
});

test("validateFields rechaza sección sin connect (mode: detail)", () => {
  const cfg = validateDirectoryConfig({ version: 1, enabled: true, sections: [detailSectionRaw()] });
  assert.throws(() => validateFields(cfg.sections[0], {}), ValidationError);
});

// ─── Paginación (scroll infinito): {{offset}}/{{limit}}, isPaginatedSource ──

test("isPaginatedSource detecta {{offset}} en la url, con o sin espacios", () => {
  assert.equal(isPaginatedSource("https://x.com/a?offset={{offset}}"), true);
  assert.equal(isPaginatedSource("https://x.com/a?offset={{ offset }}"), true);
  assert.equal(isPaginatedSource("https://x.com/a?q={{q}}"), false);
});

test("renderTemplate resuelve {{offset}}/{{limit}} como escalares top-level", () => {
  const ctx = { q: "", offset: 20, limit: 10 };
  assert.equal(renderTemplate("?offset={{offset}}&limit={{limit}}", ctx), "?offset=20&limit=10");
});

test("toPublicDirectoryDto marca paginated: true solo si source.url usa {{offset}}", () => {
  const cfg = validateDirectoryConfig({
    version: 1,
    enabled: true,
    sections: [
      { ...detailSectionRaw(), id: "noticias" },
      {
        ...detailSectionRaw(),
        id: "noticias-paginadas",
        source: { ...detailSectionRaw().source, url: "https://cliente.example.com/api/noticias?q={{q}}&offset={{offset}}&limit={{limit}}" },
      },
    ],
  });
  const dto = toPublicDirectoryDto(cfg);
  assert.equal(dto.sections.find((s) => s.id === "noticias")!.paginated, false);
  assert.equal(dto.sections.find((s) => s.id === "noticias-paginadas")!.paginated, true);
});

// ─── "conversaciones" reservado (tab incorporado, no configurable) ──────────

test("validateDirectoryConfig rechaza section.id 'conversaciones' (reservado)", () => {
  assert.throws(
    () =>
      validateDirectoryConfig({
        version: 1,
        enabled: true,
        sections: [{ ...detailSectionRaw(), id: "conversaciones" }],
      }),
    ValidationError,
  );
});
