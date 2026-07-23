import { isRunningOnVercel } from "@/lib/env";

// The no-auth CLI bypass -- ONE predicate, used from proxy.ts AND
// bot-access.ts (see management/HANDOFF_LOCAL_CLI_AND_NODES.md §4.3). Never
// duplicate this condition by hand in a second file.
//
// Real precaution taken here (see the handoff doc's "Nota de precaución
// real sobre bypasses de auth"): a previous session accidentally added an
// ad-hoc Credentials provider straight into web/auth.ts, twice, to skip
// Google login for local testing -- reverted both times, never committed.
// This is the deliberate, reviewed, committed replacement: a single skip in
// the proxy (not a fake session, not a forged JWT, not a change to
// auth.ts), gated by THREE conditions in AND:
//
//   1. !isRunningOnVercel() -- Vercel sets VERCEL=1 in every one of its
//      deploys (production, preview, `vercel dev`). This alone makes the
//      bypass structurally impossible on the real deploy -- not "someone
//      forgot a flag", genuinely unreachable code there.
//   2. process.env.PULPO_LOCAL_NO_AUTH === "1" -- explicit opt-in, set by
//      hand in web/.env.local (gitignored, never in Vercel project env
//      vars). Without this line, local dev behaves exactly like today
//      (real Google login required). `grep PULPO_LOCAL_NO_AUTH
//      web/.env.local` tells you at a glance whether it's live.
//   3. The request's Host is localhost/127.0.0.1 -- defense in depth in
//      case :9010 ever gets exposed on the LAN. Honest caveat: Host is
//      client-controlled and technically spoofable -- this is the THIRD
//      line, not the load-bearing one. Conditions 1+2, plus :9010 never
//      being reachable from the public internet, are what actually make
//      this safe.
export function isLocalNoAuth(request: Request): boolean {
  if (isRunningOnVercel()) return false;
  if (process.env.PULPO_LOCAL_NO_AUTH !== "1") return false;

  const hostHeader = request.headers.get("host") ?? "";
  const hostname = hostHeader.split(":")[0];
  return hostname === "localhost" || hostname === "127.0.0.1";
}
