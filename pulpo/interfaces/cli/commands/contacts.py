import asyncio
import json
import click
from pulpo.business import contacts as svc


@click.group()
def contacts():
    """Contact management."""


@contacts.command("list")
@click.option("--bot-id", required=True, help="Bot ID")
def list_contacts(bot_id):
    """List all contacts for a bot."""
    result = asyncio.run(svc.list_contacts(bot_id))
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@contacts.command("create")
@click.option("--bot-id", required=True, help="Bot ID")
@click.option("--name", required=True, help="Contact name")
def create_contact(bot_id, name):
    """Create a new contact for a bot (no channels; add channels separately)."""
    try:
        result = asyncio.run(svc.create_contact(bot_id=bot_id, name=name, channels=[]))
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@contacts.command("delete")
@click.argument("contact_id", type=int)
def delete_contact(contact_id):
    """Delete a contact by ID."""
    ok = asyncio.run(svc.delete_contact(contact_id))
    click.echo("Deleted." if ok else "Not found.")
