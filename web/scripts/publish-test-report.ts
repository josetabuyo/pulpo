import { readFileSync } from "node:fs";
import { upsertTestReport } from "../lib/business/test-reports";

// Sube el HTML generado por scripts/generate_e2e_report.py (Python, en la
// raíz del monorepo -- reports/test-report-e2e-<bot>-<flow_slug>.html) a la
// tabla test_reports (tab "Test" del bot card). Corre DESPUÉS de generar el
// reporte, contra la DB que corresponda (local o prod, ver DATABASE_URL en
// el env) -- publicar en ambos ambientes es correr esto dos veces, una por
// cada .env.
//
// Uso:
//   DATABASE_URL=<...> npx tsx scripts/publish-test-report.ts \
//     --bot luganense --slug orquestador_vendedor_0019d8f2 --title "Orquestador Vendedor" \
//     --file ../reports/test-report-e2e-luganense-orquestador_vendedor_0019d8f2.html
function arg(name: string): string {
  const i = process.argv.indexOf(`--${name}`);
  if (i === -1 || !process.argv[i + 1]) throw new Error(`falta --${name}`);
  return process.argv[i + 1];
}

async function main() {
  const botId = arg("bot");
  const slug = arg("slug");
  const title = arg("title");
  const filePath = arg("file");
  const html = readFileSync(filePath, "utf-8");

  await upsertTestReport({ botId, slug, title, html });
  console.log(`Publicado: bot=${botId} slug=${slug} (${html.length} bytes)`);
}

main().then(() => process.exit(0));
