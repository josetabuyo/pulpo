import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

// Same pattern as Luganense's auth.ts (Auth.js v5, session: jwt, trustHost),
// with an allowlist instead of a DB users table -- simpler, enough for this
// stage. Any Google account can complete OAuth; the signIn callback below is
// what actually gates access to the admin dashboard.
function allowedEmails(): string[] {
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
    async signIn({ profile }) {
      const email = profile?.email?.toLowerCase();
      return !!email && allowedEmails().includes(email);
    },
  },
});
