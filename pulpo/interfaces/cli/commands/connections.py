import asyncio
import json
import click
from pulpo.business import connections as svc


@click.group()
def connections():
    """Connection management (WhatsApp phone numbers)."""


@connections.command("list")
def list_connections():
    """List all connections."""
    result = asyncio.run(svc.list_connections()) if asyncio.iscoroutinefunction(svc.list_connections) else svc.list_connections()
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@connections.command("create")
@click.option("--bot-id", required=True, help="Bot ID to assign the connection to")
@click.option("--number", required=True, help="Phone number")
@click.option("--bot-name", default=None, help="Bot name (required if bot does not exist yet)")
def create_connection(bot_id, number, bot_name):
    """Create a new connection (phone number) for a bot."""
    try:
        result = svc.create_connection(bot_id=bot_id, number=number, bot_name=bot_name)
        click.echo(json.dumps(result, ensure_ascii=False))
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@connections.command("delete")
@click.argument("number")
def delete_connection(number):
    """Delete a connection by phone number."""
    ok = svc.delete_connection(number)
    click.echo("Deleted." if ok else "Not found.")
