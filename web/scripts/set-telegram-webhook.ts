import { readFileSync } from "node:fs";

// One-off: point Telegram at our new webhook for the luganense bot (plan
// step 4, management/HANDOFF_VERCEL_DEEP_MIGRATION.md). Reads the token from
// connections.json so it's never typed into a prompt or printed here. This
// STOPS the Python long-polling bot for luganense (Telegram allows only one
// delivery mode per token) -- accepted by the user, 2026-07-22.
const CONNECTIONS_JSON = "/Users/josetabuyo/Development/pulpo/_/connections.json";
const WEBHOOK_BASE = "https://pulpo-vercel-spike.vercel.app/api/telegram/webhook";

async function main() {
  const config = JSON.parse(readFileSync(CONNECTIONS_JSON, "utf-8"));
  const bot = config.bots.find((b: { id: string }) => b.id === "luganense");
  const tg = bot.telegram[0];
  const tokenId = String(tg.token).split(":")[0];
  const token = String(tg.token);

  const res = await fetch(`https://api.telegram.org/bot${token}/setWebhook`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: `${WEBHOOK_BASE}/${tokenId}` }),
  });
  const data = await res.json();
  console.log(JSON.stringify(data));
}

main().then(() => process.exit(0));
