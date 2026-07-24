// Shared "am I running local or on Vercel" gate for the local-only features
// (Wavi node, local-models LLM tier, no-auth CLI bypass -- see
// management/HANDOFF_LOCAL_CLI_AND_NODES.md §2). One helper, three
// consumers -- nobody re-derives this condition by hand.
//
// `VERCEL=1` is set by the platform in EVERY Vercel deploy (production,
// preview, and `vercel dev`) -- it's the documented, stable signal, not
// something we invented. It is NOT removable by application code.
//
// IMPORTANT gotcha found while implementing this (2026-07-23): web/.env.local
// was produced by `vercel env pull` at some point and, unless someone
// strips it, contains a literal `VERCEL="1"` line -- Next.js loads
// `.env.local` for `next dev` too, so that single line would make
// isLocalDev() report false even when running `npm run dev` on the Mac.
// Fixed by stripping the VERCEL*/pulled-Neon-prod lines from .env.local
// (see that file's header comment) -- but if `.env.local` ever gets
// re-pulled from Vercel, re-check this before trusting local dev again.
export function isRunningOnVercel(): boolean {
  return Boolean(process.env.VERCEL);
}

// The extra NODE_ENV check covers "someone runs `next start` off a
// production build on their own non-Vercel server" -- we don't want local
// features active there either, even though process.env.VERCEL is unset.
export function isLocalDev(): boolean {
  return !isRunningOnVercel() && process.env.NODE_ENV !== "production";
}
