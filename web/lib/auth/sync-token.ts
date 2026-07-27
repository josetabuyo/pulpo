// Sync-token scheme (2026-07-26, ver
// management/HANDOFF_PULPO_ENVIRONMENTS_REGISTRY.md): deja que OTRO ambiente
// Pulpo llame a las rutas de flows de este directo por HTTP, sin sesión
// humana -- header `X-Pulpo-Sync-Token` comparado contra la env var
// PULPO_SYNC_TOKEN de ESTA instancia (nunca contra `pulpo_environments`, que
// guarda los tokens que esta instancia usa para llamar a OTROS ambientes,
// no los que acepta de ellos).
export function isSyncTokenRequest(request: Request): boolean {
  const expected = process.env.PULPO_SYNC_TOKEN;
  if (!expected) return false;
  return request.headers.get("x-pulpo-sync-token") === expected;
}
