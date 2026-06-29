"""
Smoke test: todos los módulos del paquete pulpo importan sin errores.

Cubre la regresión donde 'import sim as sim_engine' a nivel módulo rompía
el startup del servidor al no encontrar 'sim' en el sys.path del nuevo paquete.
"""
import importlib
import pytest


MODULES_TO_CHECK = [
    "pulpo.interfaces.ui.app",
    "pulpo.interfaces.ui.routers.client",
    "pulpo.interfaces.ui.routers.bot_portal",
    "pulpo.interfaces.ui.routers.auth",
    "pulpo.interfaces.ui.routers.auth_bot",
    "pulpo.interfaces.api.app",
    "pulpo.interfaces.api.routers.bots",
    "pulpo.interfaces.api.routers.flows",
    "pulpo.interfaces.api.routers.architecture",
    "pulpo.business.architecture",
    "pulpo.business.bots",
    "pulpo.business.flows",
    "pulpo.business.sim",
    "pulpo.core.config",
    "pulpo.core.db",
    "pulpo.core.state",
    "pulpo.core.sim_engine",
    "pulpo.core.wavi_poller",
]


@pytest.mark.parametrize("module", MODULES_TO_CHECK)
def test_module_imports_cleanly(module):
    """Ningún módulo debe hacer import eager de 'sim' o de cualquier módulo de backend/."""
    mod = importlib.import_module(module)
    assert mod is not None


def test_no_eager_sim_import_in_client():
    """client.py no debe tener 'import sim' a nivel módulo — debe ser lazy."""
    import ast
    from pathlib import Path
    src = (
        Path(__file__).parent.parent
        / "pulpo/interfaces/ui/routers/client.py"
    ).read_text()
    tree = ast.parse(src)
    top_level_imports = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and isinstance(node.col_offset, int)
        and node.col_offset == 0
    ]
    for node in top_level_imports:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "sim", "import sim a nivel módulo en client.py"
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "sim", "from sim import ... a nivel módulo en client.py"


def test_sim_engine_sim_mode_importable():
    """SIM_MODE debe ser accesible directamente desde pulpo.core.sim_engine (no lazy)."""
    from pulpo.core.sim_engine import SIM_MODE
    assert isinstance(SIM_MODE, bool)


def test_wavi_poller_start_stop_importable():
    """start y stop deben ser accesibles directamente desde pulpo.core.wavi_poller (no lazy)."""
    from pulpo.core.wavi_poller import start, stop
    import asyncio
    assert callable(start)
    assert callable(stop)


def test_no_legacy_sim_or_wavi_poller_import_in_pulpo():
    """
    Ningún módulo de pulpo/ debe importar 'sim' o 'wavi_poller' del backend/ via sys.path hack.
    sim_engine y wavi_poller ya viven en pulpo.core.*
    """
    import ast
    from pathlib import Path

    pulpo_root = Path(__file__).parent.parent / "pulpo"
    violations = []
    for py_file in pulpo_root.rglob("*.py"):
        src = py_file.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("sim", "wavi_poller") and alias.asname in ("sim_engine", "wavi_poller", None):
                        # solo es violación si el nombre importado es el módulo bare (no pulpo.core.*)
                        if "." not in alias.name:
                            violations.append((str(py_file.relative_to(pulpo_root.parent)), alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module in ("sim", "wavi_poller"):
                    violations.append((str(py_file.relative_to(pulpo_root.parent)), node.module))
    assert not violations, f"Import bare de sim/wavi_poller encontrado (debería ser pulpo.core.*): {violations}"


def test_no_eager_sim_import_in_bot_portal():
    """bot_portal.py no debe tener 'import sim' a nivel módulo — debe ser lazy."""
    import ast
    from pathlib import Path
    src = (
        Path(__file__).parent.parent
        / "pulpo/interfaces/ui/routers/bot_portal.py"
    ).read_text()
    tree = ast.parse(src)
    top_level_imports = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and isinstance(node.col_offset, int)
        and node.col_offset == 0
    ]
    for node in top_level_imports:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "sim", "import sim a nivel módulo en bot_portal.py"
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "sim", "from sim import ... a nivel módulo en bot_portal.py"
