/**
 * E2E manual (NO es parte de `npm test` -- vive en scripts/e2e/, fuera del
 * glob `scripts/*.test.ts`): valida que el chat de Luganense con login
 * habilitado (is_public:false, ver 2026-08-17 -- chat_config
 * 80f14777-c459-4d7f-a237-8599e0213628) funcione de punta a punta en la UI
 * real -- login, envío de mensajes, sin duplicados, y persistencia de la
 * conversación entre sesiones (el problema reportado: "no recordamos
 * conversaciones anteriores" porque antes el chat era público y usaba un
 * visitorKey de localStorage en vez de una cuenta logueada).
 *
 * No automatiza el click real en "Continuar con Google" (headless OAuth
 * contra Google no es viable/apropiado) -- en cambio firma un JWT de sesión
 * de Auth.js v5 con AUTH_SECRET (mismo mecanismo que usa el propio
 * middleware para verificar la cookie) y lo inyecta directo en el browser
 * context, igual que si el usuario ya hubiese completado el login real.
 *
 * Requiere:
 *   - web/ corriendo en :9010 (ver CLAUDE.md, único puerto local)
 *   - AUTH_SECRET y DATABASE_URL de .env.local (misma DB que usa el dev server)
 *
 * Correr:
 *   npx tsx scripts/e2e/chat-login.spec.ts
 */
import { chromium } from "playwright";
import { encode } from "next-auth/jwt";
import { config as loadEnv } from "dotenv";
import path from "node:path";

loadEnv({ path: path.resolve(__dirname, "../../.env.local") });

const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:9010";
const BOT_ID = "luganense";
const CHAT_ID = "80f14777-c459-4d7f-a237-8599e0213628";
// Bot owner real (bot_users), NO admin -- ejercita el camino de
// resolveChatCaller que realmente le importa al cliente (ownsBot), no el
// atajo de admin que ya bypassea todo.
const TEST_EMAIL = "andresrodolfoprado@gmail.com";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(`FAIL: ${msg}`);
}

async function sessionCookie() {
  const secret = process.env.AUTH_SECRET;
  if (!secret) throw new Error("AUTH_SECRET no está en .env.local");
  const token = await encode({
    secret,
    salt: "authjs.session-token",
    maxAge: 60 * 60,
    token: {
      email: TEST_EMAIL,
      name: "E2E Test (Andres)",
      role: "scoped",
      botIds: [BOT_ID],
      sub: "e2e-test-andres",
    },
  });
  return {
    name: "authjs.session-token",
    value: token,
    domain: "localhost",
    path: "/",
    httpOnly: true,
    sameSite: "Lax" as const,
    expires: Math.floor(Date.now() / 1000) + 60 * 60,
  };
}

async function main() {
  console.log(`[e2e] BASE_URL=${BASE_URL} email=${TEST_EMAIL}`);

  // ── 1. Sin login: la config es privada -- listConversations debe pedir login ──
  const anonRes = await fetch(`${BASE_URL}/api/chat/${BOT_ID}/${CHAT_ID}/conversations`);
  assert(anonRes.status === 401, `esperaba 401 sin sesión, recibí ${anonRes.status}`);
  const anonBody = await anonRes.json();
  assert(anonBody.login_required === true, "esperaba login_required:true sin sesión");
  console.log("[e2e] OK: sin sesión -> 401 login_required");

  // ── 2. Con sesión (JWT firmado, simula login de Google ya completado) ──
  const browser = await chromium.launch();
  const context = await browser.newContext();
  await context.addCookies([await sessionCookie()]);
  const page = await context.newPage();

  await page.goto(`${BASE_URL}/chat/${BOT_ID}/${CHAT_ID}`);
  // No debe verse la pantalla de login (needsLogin=false con sesión válida)
  await page.waitForSelector(".pc-composer textarea", { timeout: 15000 });
  const loginScreenVisible = await page.locator(".pc-login-screen").count();
  assert(loginScreenVisible === 0, "no debería mostrarse la pantalla de login con sesión válida");
  console.log("[e2e] OK: con sesión -> entra directo al chat, sin pantalla de login");

  // El widget crea/recupera la conversación async y recién ahí navega a
  // .../c/{id} (replace) -- esperar el cambio de URL en vez de leerla ya.
  await page.waitForURL(/\/c\/[a-f0-9-]+$/, { timeout: 15000 });
  const conversationUrl = page.url();
  const conversationId = conversationUrl.split("/c/")[1];
  assert(conversationId, `no se pudo extraer conversationId de ${conversationUrl}`);
  console.log(`[e2e] conversationId=${conversationId}`);

  // ── 3. Mandar dos mensajes distintos y esperar que ambos aparezcan UNA vez ──
  const marker = Date.now().toString().slice(-6);
  const msg1 = `[e2e-${marker}] hola, primer mensaje de prueba`;
  const msg2 = `[e2e-${marker}] segundo mensaje, quiero ver noticias`;

  async function sendMessage(text: string) {
    const textarea = page.locator(".pc-composer textarea");
    await textarea.fill(text);
    await page.locator(".pc-send-btn").click();
    // El bubble propio se agrega optimista/por poll -- esperar a que aparezca
    await page.waitForFunction(
      (t) => document.body.innerText.includes(t),
      text,
      { timeout: 15000 },
    );
  }

  await sendMessage(msg1);
  await page.waitForTimeout(2000);
  await sendMessage(msg2);
  await page.waitForTimeout(4000);

  // ── 4. Sin duplicados: cada texto enviado aparece exactamente 1 vez en el DOM ──
  function countOccurrences(haystack: string, needle: string) {
    return haystack.split(needle).length - 1;
  }
  const bodyText = await page.locator("body").innerText();
  assert(countOccurrences(bodyText, msg1) === 1, `msg1 apareció ${countOccurrences(bodyText, msg1)} veces (esperaba 1)`);
  assert(countOccurrences(bodyText, msg2) === 1, `msg2 apareció ${countOccurrences(bodyText, msg2)} veces (esperaba 1)`);
  console.log("[e2e] OK: ambos mensajes aparecen exactamente una vez (sin duplicados en el DOM)");

  // ── 5. Vía API: los mensajes están en orden estrictamente creciente por id,
  //     sin ids repetidos (protege contra doble-insert por race del poll) ──
  const sessionCookieValue = (await context.cookies()).find((c) => c.name === "authjs.session-token")?.value;
  assert(sessionCookieValue, "no se encontró la cookie de sesión en el context");
  const msgsRes = await fetch(
    `${BASE_URL}/api/chat/${BOT_ID}/${CHAT_ID}/conversations/${conversationId}/messages`,
    { headers: { Cookie: `authjs.session-token=${sessionCookieValue}` } },
  );
  const msgsBody = await msgsRes.json();
  const ids: number[] = msgsBody.messages.map((m: { id: number }) => m.id);
  const uniqueIds = new Set(ids);
  assert(uniqueIds.size === ids.length, `hay ids de mensaje repetidos: ${JSON.stringify(ids)}`);
  const sorted = [...ids].sort((a, b) => a - b);
  assert(JSON.stringify(ids) === JSON.stringify(sorted), `los mensajes no llegaron en orden: ${JSON.stringify(ids)}`);
  const userTexts = msgsBody.messages.filter((m: { role: string }) => m.role === "user").map((m: { content: string }) => m.content);
  assert(userTexts.filter((t: string) => t === msg1).length === 1, "msg1 duplicado en DB");
  assert(userTexts.filter((t: string) => t === msg2).length === 1, "msg2 duplicado en DB");
  console.log(`[e2e] OK: ${ids.length} mensajes en DB, ids únicos y en orden, sin texto duplicado`);

  // ── 6. Persistencia entre sesiones: nueva pestaña (misma cookie), misma
  //     conversación, mismos mensajes -- esto es lo que reportó el usuario
  //     como roto (antes: chat público, sin login, sin memoria real) ──
  const page2 = await context.newPage();
  await page2.goto(`${BASE_URL}/chat/${BOT_ID}/${CHAT_ID}`);
  await page2.waitForSelector(".pc-composer textarea", { timeout: 15000 });
  await page2.waitForURL(/\/c\/[a-f0-9-]+$/, { timeout: 15000 });
  const url2 = page2.url();
  const conversationId2 = url2.split("/c/")[1];
  assert(conversationId2 === conversationId, `nueva sesión debería reabrir la misma conversación (${conversationId}), abrió ${conversationId2}`);
  await page2.waitForFunction((t) => document.body.innerText.includes(t), msg2, { timeout: 15000 });
  const bodyText2 = await page2.locator("body").innerText();
  assert(bodyText2.includes(msg1) && bodyText2.includes(msg2), "la conversación anterior no persistió al recargar (mismo login)");
  console.log("[e2e] OK: al reabrir con la misma sesión, se recupera la MISMA conversación con el historial completo");

  await browser.close();
  console.log("\n[e2e] TODO OK -- login gating, sin duplicados, persistencia entre sesiones.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
