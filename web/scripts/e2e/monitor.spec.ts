/**
 * E2E manual (NO es parte de `npm test` -- vive en scripts/e2e/, fuera del
 * glob `scripts/*.test.ts`, mismo patrón que chat-login.spec.ts): valida que
 * el Monitor (frontend/src/components/MonitorPanel.jsx, tab "Ejecuciones" de
 * un bot) realmente refleja actividad nueva -- manda mensajes por el chat
 * web (nodo chat, motor TS de web/) y verifica que /api/runs/stats suma un
 * éxito, tanto por API como visualmente en la UI (Monitor ya expandido por
 * default, ver RunsTab.jsx).
 *
 * Por qué chat web y no Telegram: en LOCAL, Telegram de Luganense hoy lo
 * procesa el backend Python (long-polling, SQLite local data/messages.db) --
 * desconectado de la Postgres que lee /api/runs/stats. Solo el chat web pasa
 * por el motor TS de web/ y escribe flow_runs en la Postgres correcta. En
 * PROD (Vercel) sí puede haber webhook de Telegram apuntando a web/ -- este
 * script no depende de eso, usa el chat web en cualquier ambiente.
 *
 * El mensaje "busco una ferretería" está tomado de
 * tests/e2e/luganense/test_conectividad_telegram.py -- dispara una respuesta
 * del flow "Orquestador Vendedor" de forma confiable (no queda colgado en
 * waiting_gate).
 *
 * Requiere:
 *   - web/ corriendo en :9010 (ver CLAUDE.md, único puerto local)
 *   - AUTH_SECRET y DATABASE_URL de .env.local (misma DB que usa el dev server)
 *
 * Correr contra local:
 *   npx tsx scripts/e2e/monitor.spec.ts
 * Correr contra otro ambiente (ej. prod), con su propio AUTH_SECRET:
 *   E2E_BASE_URL=https://pulpo-bot.vercel.app E2E_CHAT_ID=<chat_config.id de prod> \
 *   E2E_ENV_FILE=/ruta/a/.env.prod npx tsx scripts/e2e/monitor.spec.ts
 */
import { chromium } from "playwright";
import { encode } from "next-auth/jwt";
import { config as loadEnv } from "dotenv";
import path from "node:path";
import fs from "node:fs";

loadEnv({ path: path.resolve(__dirname, "../../.env.local") });
if (process.env.E2E_ENV_FILE) loadEnv({ path: process.env.E2E_ENV_FILE, override: true });

// Puerto único local de Pulpo: sin E2E_BASE_URL explícito, este script SOLO
// corre contra el puerto que .agent.json (protocolo `las ports`, ver
// CLAUDE.md) tiene registrado para "web/ (Next.js)" -- nunca :5173
// (deprecado) ni un puerto ad-hoc que pueda estar reclamado por otro agente
// de la sociedad. Validación real (no hardcodeada dos veces): lee el puerto
// del registro en vez de repetir el número acá.
function localPulpoWebUrl(): string {
  const agentJson = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../../../../.agent.json"), "utf8"));
  const port = agentJson.ports?.find((p: { app: string }) => p.app.startsWith("web/ (Next.js"))?.port;
  if (!port) throw new Error("FAIL: no se encontró el puerto de web/ en .agent.json");
  return `http://localhost:${port}`;
}

const BASE_URL = process.env.E2E_BASE_URL || localPulpoWebUrl();
const BOT_ID = "luganense";
// chat_config.id difiere entre DB local (:9011) y prod (Neon) -- mismo default
// que chat-login.spec.ts, overridable con E2E_CHAT_ID.
const CHAT_ID = process.env.E2E_CHAT_ID || "80f14777-c459-4d7f-a237-8599e0213628";
// Bot owner real (bot_users), NO admin -- mismo criterio que chat-login.spec.ts.
const TEST_EMAIL = "andresrodolfoprado@gmail.com";
// Ventana chica: pollMs de 3s (MonitorPanel.jsx TIME_WINDOWS) y bucket de 1min.
const STATS_WINDOW = "15m";
const POLL_TIMEOUT_MS = 60_000;
const POLL_INTERVAL_MS = 3_000;

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
    domain: new URL(BASE_URL).hostname,
    path: "/",
    httpOnly: true,
    sameSite: "Lax" as const,
    expires: Math.floor(Date.now() / 1000) + 60 * 60,
  };
}

async function fetchSuccessCount(cookieHeader: string): Promise<number> {
  const res = await fetch(`${BASE_URL}/api/runs/stats?since=${STATS_WINDOW}&botId=${BOT_ID}`, {
    headers: { Cookie: cookieHeader },
  });
  assert(res.ok, `/api/runs/stats devolvió ${res.status}`);
  const body = (await res.json()) as { buckets: { success: number }[] };
  return body.buckets.reduce((acc, b) => acc + b.success, 0);
}

async function waitForSuccessIncrement(cookieHeader: string, baseline: number): Promise<number> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const count = await fetchSuccessCount(cookieHeader);
    if (count > baseline) return count;
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }
  throw new Error(
    `FAIL: /api/runs/stats no reflejó un nuevo éxito tras ${POLL_TIMEOUT_MS}ms (baseline=${baseline})`,
  );
}

async function main() {
  console.log(`[e2e] BASE_URL=${BASE_URL} email=${TEST_EMAIL}`);

  const browser = await chromium.launch();
  const context = await browser.newContext();
  await context.addCookies([await sessionCookie()]);
  const cookieHeader = `authjs.session-token=${(await context.cookies())[0].value}`;

  // ── 1. Baseline: éxitos actuales antes de mandar nada ──
  const baseline = await fetchSuccessCount(cookieHeader);
  console.log(`[e2e] baseline de éxitos en ventana ${STATS_WINDOW}: ${baseline}`);

  // ── 2. Mandar un mensaje real por el chat web (dispara el flow) ──
  const page = await context.newPage();
  await page.goto(`${BASE_URL}/chat/${BOT_ID}/${CHAT_ID}`);
  await page.waitForSelector(".pc-composer textarea", { timeout: 15000 });
  await page.waitForURL(/\/c\/[a-f0-9-]+$/, { timeout: 15000 });

  const marker = Date.now().toString().slice(-6);
  const msg = `[e2e-monitor-${marker}] busco una ferretería`;
  const textarea = page.locator(".pc-composer textarea");
  await textarea.fill(msg);
  await page.locator(".pc-send-btn").click();
  await page.waitForFunction((t) => document.body.innerText.includes(t), msg, { timeout: 15000 });
  console.log("[e2e] mensaje enviado, esperando respuesta del flow...");

  // Esperar la respuesta del bot (bubble nuevo aparte del propio) antes de
  // consultar el Monitor -- si el run todavía está "running", no cuenta
  // como éxito hasta terminar (completed/handed_off, ver run-stats.ts).
  await page.waitForTimeout(4000);

  // ── 3. Vía API: /api/runs/stats debe reflejar el incremento ──
  const afterApi = await waitForSuccessIncrement(cookieHeader, baseline);
  console.log(`[e2e] OK vía API: éxitos pasaron de ${baseline} a ${afterApi}`);

  // ── 4. Vía UI: navegar a la tab Ejecuciones del bot y verificar que el
  //     Monitor (expandido por default) muestra el número actualizado ──
  const uiPage = await context.newPage();
  await uiPage.goto(`${BASE_URL}/bot/${BOT_ID}`);
  await uiPage.getByText("Ejecuciones", { exact: true }).click();

  // Ya no hace falta expandir a mano -- RunsTab.jsx arranca con
  // monitorOpen=true (2026-08-24, fix "no lo vi funcionar el otro día").
  await uiPage.waitForSelector(".mon-inline", { timeout: 10000 });
  const expandBtn = uiPage.getByRole("button", { name: /Expandir/ });
  assert((await expandBtn.count()) === 0, "el Monitor debería estar expandido por default, no colapsado");

  // El stat card "Éxitos" debe llegar al valor actualizado dentro del
  // pollMs de la ventana 15m (3000ms, ver TIME_WINDOWS en MonitorPanel.jsx)
  // -- damos un margen generoso para no ser flaky.
  await uiPage.waitForFunction(
    (expected) => {
      const cards = Array.from(document.querySelectorAll(".mon-stat"));
      const exitos = cards.find((c) => c.textContent?.includes("Éxitos"));
      const value = exitos?.querySelector(".mon-stat-value")?.textContent;
      return value != null && parseInt(value, 10) >= expected;
    },
    afterApi,
    { timeout: 15000 },
  );
  console.log(`[e2e] OK vía UI: stat card "Éxitos" muestra >= ${afterApi} sin refrescar la página a mano`);

  await browser.close();
  console.log("\n[e2e] TODO OK -- el Monitor refleja actividad nueva del chat web, por API y por UI.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
