import asyncio
import json
import click
from pulpo.business import flows as svc


@click.group()
def flows():
    """Flow management."""


@flows.command("list")
@click.option("--bot-id", required=True, help="Bot ID")
def list_flows(bot_id):
    result = asyncio.run(svc.list_flows(bot_id))
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@flows.command("get")
@click.option("--bot-id", required=True)
@click.option("--flow-id", required=True)
def get_flow(bot_id, flow_id):
    result = asyncio.run(svc.get_flow(flow_id, bot_id))
    if not result:
        click.echo("Flow not found.", err=True)
        raise SystemExit(1)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@flows.command("create")
@click.option("--bot-id", required=True)
@click.option("--name", required=True)
@click.option("--connection-id", default=None)
def create_flow(bot_id, name, connection_id):
    result = asyncio.run(svc.create_flow(bot_id=bot_id, name=name, connection_id=connection_id, definition=None, contact_phone=None, contact_filter=None))
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@flows.command("update")
@click.option("--bot-id", required=True)
@click.option("--flow-id", required=True)
@click.option("--field", multiple=True, type=(str, str), metavar="KEY VALUE", help="Field to update (repeat for multiple)")
def update_flow(bot_id, flow_id, field):
    """Update flow fields. Example: --field name 'New Name' --field active true"""
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


@flows.command("delete")
@click.option("--bot-id", required=True)
@click.option("--flow-id", required=True)
def delete_flow(bot_id, flow_id):
    ok = asyncio.run(svc.delete_flow(bot_id, flow_id))
    click.echo("Deleted." if ok else "Not found.")


@flows.command("node-types")
def node_types():
    result = svc.list_node_types()
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
