import asyncio
import json
import click
from pulpo.business import flows as svc


@click.group()
def flows():
    """
    Administración de flows (list, get, create, duplicate, update, delete, node-types).

    Un flow pertenece a un bot (--bot-id) y tiene un campo `active`: solo los
    flows activos aparecen en la card de bot del frontend y responden a
    mensajes entrantes. Los inactivos quedan "Guardados" — visibles pero
    sin ejecutarse — hasta que se reactivan.
    """


@flows.command("list")
@click.option("--bot-id", required=True, help="Bot ID")
def list_flows(bot_id):
    """Lista todos los flows (activos e inactivos) de un bot."""
    result = asyncio.run(svc.list_flows(bot_id))
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@flows.command("get")
@click.option("--bot-id", required=True, help="Bot ID dueño del flow")
@click.option("--flow-id", required=True, help="ID del flow")
def get_flow(bot_id, flow_id):
    """Muestra un flow completo (incluye definition: nodos y edges)."""
    result = asyncio.run(svc.get_flow(flow_id, bot_id))
    if not result:
        click.echo("Flow not found.", err=True)
        raise SystemExit(1)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@flows.command("create")
@click.option("--bot-id", required=True, help="Bot ID dueño del flow")
@click.option("--name", required=True, help="Nombre del flow")
@click.option("--connection-id", default=None, help="ID de la conexión (WhatsApp/Telegram) que dispara el flow")
def create_flow(bot_id, name, connection_id):
    """Crea un flow vacío (sin nodos). Para duplicar uno existente, usar 'duplicate'."""
    result = asyncio.run(svc.create_flow(bot_id=bot_id, name=name, connection_id=connection_id, definition=None, contact_phone=None, contact_filter=None))
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@flows.command("update")
@click.option("--bot-id", required=True, help="Bot ID dueño del flow")
@click.option("--flow-id", required=True, help="ID del flow a actualizar")
@click.option("--field", multiple=True, type=(str, str), metavar="KEY VALUE", help="Campo a actualizar (repetir para varios)")
def update_flow(bot_id, flow_id, field):
    """
    Actualiza campos de un flow. Ej: --field name 'Nuevo nombre' --field active true

    Este es el comando para activar/desactivar un flow desde CLI (equivalente
    al switch pastilla del editor visual y al botón ●/○ de la lista):

        pulpo flows update --bot-id <bot> --flow-id <id> --field active true
        pulpo flows update --bot-id <bot> --flow-id <id> --field active false

    Campos válidos: name, definition, connection_id, contact_phone,
    contact_filter, active.
    """
    updates = {}
    for k, v in field:
        if v.lower() in ("true", "false"):
            updates[k] = v.lower() == "true"
        else:
            try:
                updates[k] = json.loads(v)
            except (json.JSONDecodeError, ValueError):
                updates[k] = v
    try:
        result = asyncio.run(svc.update_flow(bot_id, flow_id, updates))
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, KeyError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@flows.command("duplicate")
@click.option("--bot-id", required=True, help="Bot ID dueño del flow")
@click.option("--flow-id", required=True, help="ID del flow a duplicar")
@click.option("--name", required=True, help="Nombre del flow nuevo (la copia)")
def duplicate_flow(bot_id, flow_id, name):
    """
    Duplica un flow existente con un nuevo nombre.

    Copia definition, connection_id, contact_phone y contact_filter del
    flow original. El duplicado queda INACTIVO para no competir en paralelo
    con el original — activalo después con:

        pulpo flows update --bot-id <bot> --flow-id <id-nuevo> --field active true

    Equivalente al botón "Guardar como" del editor visual (frontend).
    """
    try:
        result = asyncio.run(svc.duplicate_flow(bot_id, flow_id, name))
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@flows.command("delete")
@click.option("--bot-id", required=True, help="Bot ID dueño del flow")
@click.option("--flow-id", required=True, help="ID del flow a eliminar")
def delete_flow(bot_id, flow_id):
    """Elimina un flow. Esta acción no se puede deshacer (usar 'update --field active false' si solo se quiere pausarlo)."""
    ok = asyncio.run(svc.delete_flow(bot_id, flow_id))
    click.echo("Deleted." if ok else "Not found.")


@flows.command("simulate")
@click.option("--bot-id", required=True, help="Bot a la que simular el mensaje")
@click.option("--message", required=True, help="Mensaje de entrada del usuario simulado")
@click.option("--sim-id", default=None, help="ID de la simulación (para continuar una conversación existente)")
@click.option("--contact-name", default="Simulación", help="Nombre de contacto mostrado en la simulación")
def simulate_message(bot_id, message, sim_id, contact_name):
    """
    Manda un mensaje simulado a una bot sin pasar por Telegram/WhatsApp real
    (in-band, ver management/HANDOFF_SIMULACION_V2.md) — equivalente a
    mandarlo por Telegram: el flow/trigger que aplica se resuelve solo,
    igual que con un mensaje real.

    Reusar el mismo --sim-id en llamadas sucesivas continúa la misma
    conversación simulada, incluso a través de un wait_user.
    """
    try:
        result = asyncio.run(
            svc.simulate_message(
                bot_id=bot_id,
                message=message,
                sim_id=sim_id,
                contact_name=contact_name,
            )
        )
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@flows.command("node-types")
def node_types():
    """Lista el catálogo de tipos de nodo disponibles para armar flows (id, label, schema de config)."""
    result = svc.list_node_types()
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@flows.command("node-flows")
@click.option("--bot-id", required=True, help="Bot ID")
def node_flows(bot_id):
    """
    Lista los NodoFlows disponibles de un bot (flows con flow_kind=node_flow),
    con sus `inputs` declarados — útil para saber qué flow_id/params configurar
    en un nodo `nodo_flow` de otro flow.
    """
    result = asyncio.run(svc.list_node_flows(bot_id))
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@flows.command("extract-node-flow")
@click.option("--bot-id", required=True, help="Bot ID dueño del flow origen")
@click.option("--flow-id", required=True, help="ID del flow origen del que se extrae la selección")
@click.option("--node-ids", required=True, help="IDs de nodo a extraer, separados por coma (a,b,c)")
@click.option("--name", required=True, help="Nombre del NodoFlow nuevo")
def extract_node_flow(bot_id, flow_id, node_ids, name):
    """
    Extrae los nodos indicados (+ sus edges internos) de un flow existente en
    un NodoFlow nuevo (flow_kind=node_flow, active=false). El flow origen no
    se modifica — equivalente a "Convertir selección en NodoFlow" del editor.
    """
    ids = [n.strip() for n in node_ids.split(",") if n.strip()]
    try:
        result = asyncio.run(
            svc.create_node_flow_from_selection(
                bot_id=bot_id, source_flow_id=flow_id, node_ids=ids, name=name,
            )
        )
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
