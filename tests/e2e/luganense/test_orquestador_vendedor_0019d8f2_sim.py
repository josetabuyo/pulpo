"""
E2E (simulado) — Orquestador Vendedor Mejorado / bot Luganense.

Wrapper delgado sobre `scenarios_orquestador_vendedor_mejorado.py` (fuente
única compartida con `scripts/generate_e2e_report.py` — mismas
conversaciones, mismas validaciones, sin duplicar lógica entre el test y el
reporte).

Nombres de test: `test_<bot_slug>__<flow_slug>__<scenario_id>` (ver
BOT_SLUG/FLOW_SLUG en el módulo de escenarios) — así `pytest -k luganense`
filtra todo el bot, `pytest -k orquestador_vendedor_mejorado` filtra este
flow puntual, y cuando el bot tenga un segundo flow activo sus tests no
colisionan de nombre ni de filtro con estos.

Revisión 2026-07-10 (v2, tras feedback): cada escenario es una conversación
COMPLETA de punta a punta — arranca en el trigger real y SIEMPRE llega a un
`end_conversation` real, incluso el único caso infeliz (agotamiento de
reintentos de dirección). Nada de conversaciones que terminan a mitad de
camino (ej. un test que solo manda "hola" y no sigue — eso no es un caso e2e
válido). Las validaciones leen el LOG REAL de ejecución (`flow_run_steps` vía
`SimConversation.step/ran_node/state_field/branch_taken`), no solo texto
suelto del reply.

Requiere solo el backend local corriendo (`http://localhost:8000` por
default), sin `ENABLE_BOTS`/teli — excepto el escenario de conectividad, que
vive aparte en `test_conectividad_telegram.py` (único test real con Telegram
de toda esta suite).
"""
import asyncio

import pytest

from tests.e2e.luganense.scenarios_orquestador_vendedor_mejorado import SCENARIOS, BOT_SLUG, FLOW_SLUG

pytestmark = pytest.mark.e2e_sim


def _run(coro):
    return asyncio.run(coro)


def _make_test(scenario):
    def test_fn():
        result = _run(scenario.run())
        # Solo "assert" hace fallar el test — "log" es informativo (decisiones
        # semánticas de un LLM, no deterministas, ver docstring del módulo de
        # escenarios). Se imprimen igual en el mensaje de falla, para diagnóstico.
        failed = [c for c in result.checks if c.kind == "assert" and not c.passed]
        logs = [c for c in result.checks if c.kind == "log"]
        if failed:
            transcript = "\n".join(f"  [{role}] {text}" for role, text in result.turns)
            detail_lines = "\n".join(f"  ✗ {c.label}" + (f" — {c.detail}" if c.detail else "") for c in failed)
            log_lines = "\n".join(f"  · {c.label}" + (f" — {c.detail}" if c.detail else "") for c in logs)
            pytest.fail(
                f"\n{len(failed)}/{len([c for c in result.checks if c.kind == 'assert'])} asserts fallaron en \"{scenario.title}\":\n"
                f"{detail_lines}\n\nLogs informativos (no determinan pass/fail):\n{log_lines}\n\n"
                f"Conversación completa:\n{transcript}"
            )
    test_fn.__name__ = f"test_{BOT_SLUG}__{FLOW_SLUG}__{scenario.id.replace('-', '_')}"
    test_fn.__doc__ = scenario.desc
    return test_fn


for _scenario in SCENARIOS:
    if _scenario.real_telegram:
        continue  # vive en test_conectividad_telegram.py, no acá
    _test_name = f"test_{BOT_SLUG}__{FLOW_SLUG}__{_scenario.id.replace('-', '_')}"
    globals()[_test_name] = _make_test(_scenario)
