export const SENTINEL = Symbol("not-found");

export function resolveJsonPath(parsed: unknown, path: string): unknown {
  let current: unknown = parsed;
  if (path === "") return current;
  for (const part of path.split(".")) {
    if (current !== null && typeof current === "object" && !Array.isArray(current)) {
      const obj = current as Record<string, unknown>;
      if (!(part in obj)) return SENTINEL;
      current = obj[part];
    } else if (Array.isArray(current)) {
      if (!/^-?\d+$/.test(part)) return SENTINEL;
      const idx = Number(part);
      const realIdx = idx < 0 ? current.length + idx : idx;
      if (realIdx < 0 || realIdx >= current.length) return SENTINEL;
      current = current[realIdx];
    } else {
      return SENTINEL;
    }
  }
  return current;
}
