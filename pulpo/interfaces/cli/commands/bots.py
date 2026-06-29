import asyncio
import json
import click
from pulpo.business import bots as svc


@click.group()
def bots():
    """Bot management."""


@bots.command("list")
def list_bots():
    """List all bots."""
    result = asyncio.run(svc.list_bots()) if asyncio.iscoroutinefunction(svc.list_bots) else svc.list_bots()
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@bots.command("create")
@click.argument("id")
@click.option("--name", required=True)
@click.option("--password", required=True)
def create_bot(id, name, password):
    """Create a new bot."""
    try:
        result = svc.create_bot(id, name, password)
        click.echo(json.dumps(result, ensure_ascii=False))
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@bots.command("delete")
@click.argument("bot_id")
def delete_bot(bot_id):
    """Delete a bot."""
    ok = svc.delete_bot(bot_id)
    click.echo("Deleted." if ok else "Not found.")
