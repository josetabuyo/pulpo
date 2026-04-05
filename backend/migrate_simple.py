#!/usr/bin/env python3
"""
Migración simple de flows legacy usando SQL directo.
"""
import sqlite3
import json

DB_PATH = "/Users/josetabuyo/Development/pulpo/_/data/messages.db"

def migrate_definition(definition_str):
    """Migra la definición JSON de un flow."""
    try:
        definition = json.loads(definition_str)
    except json.JSONDecodeError:
        return definition_str

    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])
    changed = False

    # Migrar nodos start
    for node in nodes:
        node_id = node.get("id", "")
        node_type = node.get("type", "")

        # Migrar __start__ como id o start como type
        if node_id == "__start__" or node_type == "start":
            node["id"] = "message_trigger_1"
            node["type"] = "message_trigger"
            # Configuración vacía por defecto
            if "config" not in node:
                node["config"] = {}
            changed = True

    # Migrar edges
    for edge in edges:
        if edge.get("source") == "__start__":
            edge["source"] = "message_trigger_1"
            changed = True
        if edge.get("target") == "__start__":
            edge["target"] = "message_trigger_1"
            changed = True

    if changed:
        return json.dumps(definition)
    return definition_str

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Contar flows a migrar
    cursor.execute("SELECT COUNT(*) FROM flows WHERE definition LIKE '%__start__%' OR definition LIKE '%\"start\"%'")
    count = cursor.fetchone()[0]
    print(f"Flows a migrar: {count}")

    # Obtener todos los flows
    cursor.execute("SELECT id, name, definition FROM flows")
    flows = cursor.fetchall()

    migrated = 0
    for flow_id, name, definition in flows:
        new_definition = migrate_definition(definition)
        if new_definition != definition:
            cursor.execute(
                "UPDATE flows SET definition = ? WHERE id = ?",
                (new_definition, flow_id)
            )
            print(f"✓ {name} ({flow_id}) migrado")
            migrated += 1

    conn.commit()
    conn.close()

    print(f"\n✅ {migrated} flows migrados de {len(flows)} totales")

if __name__ == "__main__":
    main()