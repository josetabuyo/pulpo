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
