import asyncio
import json
import click
from pulpo.business import messages as svc


@click.group()
def messages():
    """Message management."""


@messages.command("list")
@click.option("--limit", default=100, show_default=True, help="Max number of messages to return")
def list_messages(limit):
    """List recent messages."""
    result = asyncio.run(svc.list_messages(limit=limit))
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
