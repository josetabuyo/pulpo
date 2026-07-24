import type { DefaultSession } from "next-auth";

// Adds role/botIds to the session/JWT shape auth.ts populates -- see the
// comment there for what these mean (Pulpo PRO/Lite, paso 1).
declare module "next-auth" {
  interface Session {
    user: {
      role?: "admin" | "scoped";
      botIds?: string[];
    } & DefaultSession["user"];
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    role?: "admin" | "scoped";
    botIds?: string[];
  }
}
