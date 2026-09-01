import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";
import type { Provider } from "@auth/core/providers";
import { listBotsForEmail } from "@/lib/business/bot-users";
import { isLocalDev } from "@/lib/env";

// Same pattern as Luganense's auth.ts (Auth.js v5, session: jwt, trustHost).
// Any Google account can complete OAuth; the signIn callback below is what
// actually gates access.
//
// One login, two roles (2026-07-22, paso 1 hacia Pulpo PRO/Lite): "admin"
// (ALLOWED_ADMIN_EMAILS, ve todo -- lo que hoy es el dashboard) o "scoped"
// (email registrado en bot_users, ve solo los bots de su allowlist -- PRO si
// tiene varios, Lite si tiene uno solo, mismo mecanismo para ambos, ver
// lib/db/schema.ts::botUsers). proxy.ts es quien realmente hace cumplir esto
// -- ver ese archivo. Hoy "scoped" no tiene ninguna ruta habilitada todavía
// (el portal /bot/{id} en sí es un paso posterior); este cambio solo deja la
// base de auth lista.
function allowedAdminEmails(): string[] {
  return (process.env.ALLOWED_ADMIN_EMAILS || "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

// Bypass de login para e2e/dev local -- mismo problema que ya resolvió
// Luganense (components/LoginPage.tsx + auth.ts, provider "fake-login"
// gateado por NODE_ENV): Playwright no puede completar un OAuth real contra
// Google. Gateado acá con isLocalDev() (lib/env.ts: !VERCEL && NODE_ENV !==
// "production") en vez de un chequeo propio -- ES el mismo predicado ya
// usado por el CLI y el router local (management/HANDOFF_LOCAL_CLI_AND_NODES.md
// §2), no una condición nueva a mantener sincronizada por separado.
// Evaluado UNA vez al cargar el módulo: en cualquier build real de Vercel
// (preview o producción, ambos corren `next build` → NODE_ENV=production)
// este provider directamente no se registra, no es que quede oculto en la
// UI -- no existe en ese proceso.
//
// A diferencia del "fake-login" de Luganense (que consulta su propia tabla
// `users`), authorize() acá NO decide nada de autorización -- solo valida
// que venga un email y se lo pasa a NextAuth. La decisión real (admin vs
// scoped vs rechazado) la sigue haciendo el callback signIn() de abajo,
// EXACTAMENTE la misma lógica que un login real de Google -- un email de
// prueba pasa por el mismo allowedAdminEmails()/listBotsForEmail() que
// pasaría con Google, cero lógica de autorización duplicada.
//
// Nota histórica (ver lib/auth/local-bypass.ts): una sesión anterior había
// agregado un Credentials provider ad-hoc acá mismo, dos veces, y lo revirtió
// sin comittear por apuro/falta de revisión -- no porque se haya encontrado
// una falla de seguridad concreta. Esta vez queda documentado y con el
// mismo gate ya establecido y revisado que usa el resto del bypass local.
const providers: Provider[] = [
  Google({
    clientId: process.env.AUTH_GOOGLE_ID,
    clientSecret: process.env.AUTH_GOOGLE_SECRET,
  }),
];

if (isLocalDev()) {
  providers.push(
    Credentials({
      id: "test-login",
      name: "Test Login (solo local/e2e)",
      credentials: { email: { label: "Email", type: "email" } },
      async authorize(credentials) {
        const email = typeof credentials?.email === "string" ? credentials.email.trim() : "";
        if (!email) return null;
        return { id: email, email, name: email };
      },
    }),
  );
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers,
  session: { strategy: "jwt" },
  trustHost: true,
  pages: { signIn: "/" },
  callbacks: {
    async signIn({ profile, user }) {
      const email = profile?.email?.toLowerCase() || user?.email?.toLowerCase();
      if (!email) return false;
      if (allowedAdminEmails().includes(email)) return true;
      const botIds = await listBotsForEmail(email);
      return botIds.length > 0;
    },
    async jwt({ token }) {
      const email = token.email?.toLowerCase();
      if (!email) return token;
      if (allowedAdminEmails().includes(email)) {
        token.role = "admin";
        token.botIds = [];
      } else {
        token.role = "scoped";
        token.botIds = await listBotsForEmail(email);
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.role = token.role as "admin" | "scoped" | undefined;
        session.user.botIds = token.botIds as string[] | undefined;
      }
      return session;
    },
  },
});
