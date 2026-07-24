import { SignJWT, jwtVerify } from "jose";

// TS port of the JWT half of pulpo/core/auth_jwt.py, with the root-cause fix
// from the spike plan: JWT_SECRET_KEY has NO random fallback. Missing env var
// is a hard failure, not a silently-rotating secret (the Python version does
// `os.environ.get("JWT_SECRET_KEY", secrets.token_hex(32))`, which invalidates
// every token on every process restart).
const ACCESS_TOKEN_EXPIRE_MINUTES = 30;

function getSecret(): Uint8Array {
  const secret = process.env.JWT_SECRET_KEY;
  if (!secret) throw new Error("JWT_SECRET_KEY is not set");
  return new TextEncoder().encode(secret);
}

export async function createAccessToken(subject: string): Promise<string> {
  return new SignJWT({ sub: subject })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${ACCESS_TOKEN_EXPIRE_MINUTES}m`)
    .sign(getSecret());
}

export async function verifyAccessToken(token: string): Promise<string | null> {
  try {
    const { payload } = await jwtVerify(token, getSecret());
    return typeof payload.sub === "string" ? payload.sub : null;
  } catch {
    return null;
  }
}
