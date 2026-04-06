"""
Tests para VectorSearchNode.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from graphs.nodes.vector_search import VectorSearchNode
from graphs.nodes.state import FlowState
from graphs.collections import COLLECTION_REGISTRY


@pytest.mark.asyncio
async def test_vector_search_node_config_schema():
    """El nodo tiene un schema de configuración válido."""
    schema = VectorSearchNode.config_schema()
    assert "collection" in schema
    assert "query_field" in schema
    assert "output_field" in schema
    assert "top_k" in schema

    assert schema["collection"]["required"] is True
    assert schema["query_field"]["default"] == "message"
    assert schema["output_field"]["default"] == "context"
    assert schema["top_k"]["default"] == 3


@pytest.mark.asyncio
async def test_vector_search_sin_coleccion():
    """Si no se especifica colección, continúa sin romper el flow."""
    config = {}
    node = VectorSearchNode(config)
    state = FlowState(message="Necesito un electricista")
    result = await node.run(state)
    assert result is state  # retorna sin modificar


@pytest.mark.asyncio
async def test_vector_search_coleccion_no_existe():
    """Si la colección no existe, loguea warning y continúa sin romper."""
    config = {"collection": "coleccion_inexistente"}
    node = VectorSearchNode(config)
    state = FlowState(message="Necesito un electricista", empresa_id="bot_test")
    result = await node.run(state)
    assert result is state  # retorna sin modificar


@pytest.mark.asyncio
async def test_vector_search_registrados():
    """Las colecciones de Luganense están registradas."""
    assert "luganense_oficios" in COLLECTION_REGISTRY
    assert "luganense_auspiciantes" in COLLECTION_REGISTRY


@pytest.mark.asyncio
async def test_vector_search_oficios_handler_existe():
    """El handler de luganense_oficios existe y es callable."""
    handler = COLLECTION_REGISTRY.get("luganense_oficios")
    assert handler is not None
    assert callable(handler)


@pytest.mark.asyncio
async def test_vector_search_auspiciantes_handler_existe():
    """El handler de luganense_auspiciantes existe y es callable."""
    handler = COLLECTION_REGISTRY.get("luganense_auspiciantes")
    assert handler is not None
    assert callable(handler)


@pytest.mark.asyncio
async def test_vector_search_query_field_message():
    """Lee el query del campo message (default)."""
    config = {"collection": "luganense_oficios", "query_field": "message"}
    node = VectorSearchNode(config)

    state = FlowState(
        message="Necesito un electricista",
        empresa_id="bot_test"
    )
    result = await node.run(state)

    # El handler debe haber escrito en state.vars
    assert "oficio" in result.vars
    assert "worker" in result.vars


@pytest.mark.asyncio
async def test_vector_search_output_field_context():
    """Escribe el resultado en state.context (default)."""
    config = {"collection": "luganense_oficios"}
    node = VectorSearchNode(config)

    state = FlowState(
        message="Necesito un electricista",
        empresa_id="bot_test"
    )
    result = await node.run(state)

    # El resultado debe estar en state.context (serializado como JSON)
    assert result.context is not None
    assert result.context != ""


@pytest.mark.asyncio
async def test_vector_search_interpola_placeholders():
    """Interpola placeholders en el query."""
    config = {
        "collection": "luganense_oficios",
        "query_field": "message",
    }
    node = VectorSearchNode(config)

    # El mensaje tiene placeholders que deben interpolarse
    state = FlowState(
        message="Necesito {{message}}",  # placeholder
        empresa_id="bot_test"
    )
    # Nota: {{message}} es un placeholder self-referencial, debería quedar igual
    result = await node.run(state)
    assert "oficio" in result.vars


@pytest.mark.asyncio
async def test_vector_search_vars_tienen_todas_las_keys():
    """El handler retorna todas sus keys en state.vars."""
    config = {"collection": "luganense_oficios"}
    node = VectorSearchNode(config)

    state = FlowState(
        message="Necesito un electricista",
        empresa_id="bot_test"
    )
    result = await node.run(state)

    # El handler de oficios retorna: oficio, worker, nombre, telefono, text
    assert "oficio" in result.vars
    assert "worker" in result.vars
    assert "nombre" in result.vars
    assert "telefono" in result.vars
    assert "text" in result.vars
