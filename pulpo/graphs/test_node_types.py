"""Tests unitarios para node_types — garantiza que NODE_TYPES y NODE_REGISTRY nunca se desincronicen."""
from .node_types import NODE_TYPES, get, classify
from .nodes import NODE_REGISTRY


def test_node_types_se_deriva_de_todo_el_registry():
    assert set(NODE_TYPES.keys()) == set(NODE_REGISTRY.keys())


def test_ningun_nodo_del_registry_usa_metadata_por_defecto():
    sin_label_propio = [type_id for type_id, cls in NODE_REGISTRY.items() if cls.label == "Nodo"]
    assert sin_label_propio == [], (
        f"Estos nodos no declaran su propio label/color/description: {sin_label_propio}"
    )


def test_condition_esta_en_node_types():
    assert "condition" in NODE_TYPES
    assert NODE_TYPES["condition"].label == "Condición"


def test_get_fallback_a_generic():
    nt = get("tipo_que_no_existe")
    assert nt.id == "generic"


def test_classify_reconoce_condition_por_id():
    nt = classify("mi_nodo_condition_algo")
    assert nt.id == "condition"
