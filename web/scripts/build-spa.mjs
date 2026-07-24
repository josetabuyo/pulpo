// Build la SPA de Vite (../frontend) e integrarla al build de Next.js
// (2026-07-24, "un solo deploy"): copia los assets estáticos a public/ e
// inlinea index.html como módulo TS para que app/[[...slug]]/route.ts lo
// sirva sin depender de leer archivos en runtime (el filesystem de
// public/ no es confiable en funciones serverless de Vercel).
//
// Corre como paso previo a `next build` (ver package.json). NO se usa en
// dev local -- frontend/ sigue sirviéndose con su propio Vite dev server
// (./start.sh front), este script es solo para el build de producción.
import { execSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync, cpSync, readFileSync, writeFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const frontendDir = path.join(webDir, "..", "frontend");
const distDir = path.join(frontendDir, "dist");

// El build de Vercel solo sube el árbol del directorio linkeado (web/), no
// el monorepo entero -- frontend/ (hermano de web/) no existe ahí. En ese
// caso usamos lo que ya haya en public/assets + lib/generated/spa-index.ts
// (generado localmente ANTES de `vercel deploy` y subido igual gracias a
// .vercelignore, ver ese archivo). Local/CI con el monorepo completo sí
// regenera todo desde cero.
if (existsSync(frontendDir)) {
  console.log("[build-spa] npm install + build en frontend/...");
  execSync("npm install && npm run build", { cwd: frontendDir, stdio: "inherit" });
} else {
  console.log("[build-spa] frontend/ no está en este build (deploy solo de web/) -- uso el pre-generado.");
  if (!existsSync(path.join(webDir, "lib", "generated", "spa-index.ts"))) {
    throw new Error(
      "[build-spa] falta lib/generated/spa-index.ts y no hay frontend/ para generarlo -- " +
        "corré `node scripts/build-spa.mjs` desde el monorepo completo antes de deployar.",
    );
  }
  process.exit(0);
}

if (!existsSync(path.join(distDir, "index.html"))) {
  throw new Error(`[build-spa] no se encontró ${distDir}/index.html -- ¿falló el build de Vite?`);
}

const publicDir = path.join(webDir, "public");
mkdirSync(publicDir, { recursive: true });

// assets/ (JS/CSS con hash) -- reemplazo completo en cada build.
const publicAssetsDir = path.join(publicDir, "assets");
rmSync(publicAssetsDir, { recursive: true, force: true });
cpSync(path.join(distDir, "assets"), publicAssetsDir, { recursive: true });

// Resto de archivos sueltos de dist/ (favicon, etc.) -- todo menos
// index.html (se inlinea abajo) y assets/ (ya copiado arriba).
for (const entry of readdirSync(distDir)) {
  if (entry === "assets" || entry === "index.html") continue;
  cpSync(path.join(distDir, entry), path.join(publicDir, entry), { recursive: true });
}

const html = readFileSync(path.join(distDir, "index.html"), "utf8");
const generatedDir = path.join(webDir, "lib", "generated");
mkdirSync(generatedDir, { recursive: true });
writeFileSync(
  path.join(generatedDir, "spa-index.ts"),
  `// AUTO-GENERADO por scripts/build-spa.mjs a partir de frontend/dist/index.html -- no editar a mano.\nexport const SPA_INDEX_HTML = ${JSON.stringify(html)};\n`,
);

console.log("[build-spa] listo: public/assets/ + lib/generated/spa-index.ts");
