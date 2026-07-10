"""
E2E (simulado) — Orquestador Vendedor Mejorado / bot Luganense.

Wrapper delgado sobre `scenarios.py` (fuente única compartida con
`scripts/generate_e2e_report.py` — mismas conversaciones, mismas
validaciones, sin duplicar lógica entre el test y el reporte).

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

from tests.e2e.luganense.scenarios import SCENARIOS

pytestmark = pytest.mark.e2e_sim


def _run(coro):
    return asyncio.run(coro)


def _make_test(scenario):
    def test_fn():
        result = _run(scenario.run())
        failed = [c for c in result.checks if not c.passed]
        if failed:
            transcript = "\n".join(f"  [{role}] {text}" for role, text in result.turns)
            detail_lines = "\n".join(f"  ✗ {c.label}" + (f" — {c.detail}" if c.detail else "") for c in failed)
            pytest.fail(
                f"\n{len(failed)}/{len(result.checks)} validaciones fallaron en \"{scenario.title}\":\n"
                f"{detail_lines}\n\nConversación completa:\n{transcript}"
            )
    test_fn.__name__ = f"test_{scenario.id.replace('-', '_')}"
    test_fn.__doc__ = scenario.desc
    return test_fn


for _scenario in SCENARIOS:
    if _scenario.real_telegram:
        continue  # vive en test_conectividad_telegram.py, no acá
    globals()[f"test_{_scenario.id.replace('-', '_')}"] = _make_test(_scenario)
