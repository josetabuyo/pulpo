"""
Migración one-shot: {{message}} → {{conversation.last}} / {{conversation}}
en las definiciones de flows guardadas en DB.

Contexto: el placeholder {{message}} (mensaje entrante suelto) fue reemplazado
por data["conversation"] (array de turnos user/bot_reply de la ejecución del
flow). interpolate() ya no resuelve {{message}} — hay que migrar los flows
existentes que lo usaban en sus configs.

Reemplazos:
  - notificar_trabajador (send_message) → {{conversation.last}}
    ("lo último que dijo el vecino" — igual que antes)
  - set_direccion (set_state, value) → {{conversation.last}}
    (captura literal del turno actual)
  - node_1783357520816 (llm, prompt) → {{conversation}}
    (el nodo ahora además recibe el historial completo como mensajes
    user/assistant — el prompt referencia la transcripción, no solo el último turno)
  - node_1783194257636 (metric, metadata.mensaje) → {{conversation.last}}
    (clave de negocio "mensaje" en el payload del webhook — valor anidado
    dentro de metadata, no un field de config de primer nivel)

Uso:
  python scripts/migrate_conversation_placeholder.py [--db path] [--apply]

Sin --apply corre en modo dry-run (solo muestra el diff).
"""
import argparse
import json
import sqlite3
import sys

REPLACEMENTS = {
    "d703b474-79af-40f5-933f-895a0b634d4a": {
        "notificar_trabajador": [("{{message}}", "{{conversation.last}}")],
        "set_direccion":        [("{{message}}", "{{conversation.last}}")],
    },
    "0019d8f2-ada5-4409-99bf-50921beb875b": {
        "notificar_trabajador":     [("{{message}}", "{{conversation.last}}")],
        "set_direccion":            [("{{message}}", "{{conversation.last}}")],
        "node_1783357520816":       [("Mensaje del cliente:\n{{message}}", "Historial de la conversación:\n{{conversation}}")],
        "node_1783194257636":       [("{{message}}", "{{conversation.last}}")],
    },
}


def _patch_strings(value, patches: list[tuple[str, str]]):
    """Aplica los reemplazos recursivamente sobre str/dict/list anidados
    (ej: config["metadata"]["mensaje"] no es un field de primer nivel)."""
    if isinstance(value, str):
        new_value = value
        for old, new in patches:
            new_value = new_value.replace(old, new)
        return new_value, new_value != value
    if isinstance(value, dict):
        changed = False
        new_dict = {}
        for k, v in value.items():
            new_dict[k], sub_changed = _patch_strings(v, patches)
            changed = changed or sub_changed
        return new_dict, changed
    if isinstance(value, list):
        changed = False
        new_list = []
        for v in value:
            new_v, sub_changed = _patch_strings(v, patches)
            new_list.append(new_v)
            changed = changed or sub_changed
        return new_list, changed
    return value, False


def migrate(db_path: str, apply: bool) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    changed = 0

    for flow_id, node_patches in REPLACEMENTS.items():
        row = cur.execute("SELECT name, definition FROM flows WHERE id = ?", (flow_id,)).fetchone()
        if not row:
            print(f"[skip] flow {flow_id} no encontrado en {db_path}")
            continue
        name, raw_def = row
        definition = json.loads(raw_def)
        flow_changed = False

        for node in definition.get("nodes", []):
            patches = node_patches.get(node.get("id"))
            if not patches:
                continue
            for key, value in list(node.get("config", {}).items()):
                new_value, field_changed = _patch_strings(value, patches)
                if field_changed:
                    print(f"--- flow={name!r} node={node['id']!r} field={key!r}")
                    print(f"  antes:   {value!r}")
                    print(f"  después: {new_value!r}")
                    node["config"][key] = new_value
                    flow_changed = True

        if flow_changed:
            changed += 1
            if apply:
                cur.execute(
                    "UPDATE flows SET definition = ? WHERE id = ?",
                    (json.dumps(definition, ensure_ascii=False), flow_id),
                )

    if apply:
        con.commit()
        print(f"\n{changed} flow(s) actualizados en {db_path}")
    else:
        print(f"\n[dry-run] {changed} flow(s) tendrían cambios — correr con --apply para persistir")
    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/messages.db")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    migrate(args.db, args.apply)
