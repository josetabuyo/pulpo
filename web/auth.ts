import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import { listBotsForEmail } from "@/lib/business/bot-users";

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

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Google({
      clientId: process.env.AUTH_GOOGLE_ID,
      clientSecret: process.env.AUTH_GOOGLE_SECRET,
    }),
  ],
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
