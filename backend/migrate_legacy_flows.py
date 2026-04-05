#!/usr/bin/env python3
"""
Migra flows legacy (__start__ / input_text) al nuevo sistema de triggers.

Ejecutar una sola vez después de deployar los cambios.
Los flows migrados mantienen su connection_id y contact_phone si los tenían.
"""
import asyncio
import json
from typing import Optional

import db


async def migrate_flow(flow: dict) -> Optional[dict]:
    """Migra un flow individual si tiene nodos legacy."""
    definition = flow.get("definition", {})
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    changes_made = False

    # Buscar nodos __start__ o input_text
    for node in nodes:
        node_id = node.get("id", "")
        node_type = node.get("type", "")

        if node_id == "__start__" or node_type in ("__start__", "input_text"):
            # Convertir a message_trigger
            node["type"] = "message_trigger"
            node["id"] = "message_trigger_1"  # ID consistente

            # Preservar configuración si existe
            config = node.get("config", {})

            # Si el flow tenía connection_id/contact_phone a nivel flow,
            # moverlos al config del trigger
            if not config.get("connection_id") and flow.get("connection_id"):
                config["connection_id"] = flow.get("connection_id")
            if not config.get("contact_phone") and flow.get("contact_phone"):
                config["contact_phone"] = flow.get("contact_phone")

            node["config"] = config
            changes_made = True

    if not changes_made:
        return None

    # Actualizar edges que apuntaban al nodo viejo
    old_start_id = "__start__"
    new_start_id = "message_trigger_1"

    for edge in edges:
        if edge.get("source") == old_start_id:
            edge["source"] = new_start_id
        if edge.get("target") == old_start_id:
            edge["target"] = new_start_id

    definition["nodes"] = nodes
    definition["edges"] = edges

    # Limpiar campos legacy a nivel flow (ahora están en el trigger)
    updated_flow = flow.copy()
    updated_flow["definition"] = definition
    updated_flow.pop("connection_id", None)
    updated_flow.pop("contact_phone", None)

    return updated_flow


async def main():
    """Migra todos los flows de la base de datos."""
    print("=== Migración de flows legacy a message_trigger ===")

    # Obtener todas las empresas
    import config as cfg
    config = cfg.load_config()
    empresas = [empresa["id"] for empresa in config.get("empresas", [])]

    total_migrated = 0

    for empresa_id in empresas:
        print(f"\nProcesando empresa: {empresa_id}")

        flows = await db.get_flows(empresa_id)

        for flow in flows:
            flow_id = flow["id"]
            flow_name = flow.get("name", "sin nombre")

            migrated = await migrate_flow(flow)
            if migrated:
                # Actualizar en la base de datos
                await db.update_flow(
                    flow_id=flow_id,
                    name=migrated.get("name"),
                    definition=migrated.get("definition"),
                    active=migrated.get("active", True)
                )
                print(f"  ✓ {flow_name} ({flow_id}) migrado")
                total_migrated += 1
            else:
                print(f"  - {flow_name} ({flow_id}) ya está actualizado")

    print(f"\n✅ Migración completada: {total_migrated} flows migrados")
    print("\nNota: Los flows migrados ahora usan message_trigger con configuración")
    print("      embebida en el nodo (connection_id, contact_phone, message_pattern).")


if __name__ == "__main__":
    asyncio.run(main())