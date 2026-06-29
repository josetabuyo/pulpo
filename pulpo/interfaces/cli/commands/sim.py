import asyncio
import json
import click
from pulpo.business import sim as svc


@click.group()
def sim():
    """Simulator controls (only active when ENABLE_BOTS is not true)."""


@sim.command("mode")
def mode():
    """Show current mode (simulated or real)."""
    result = svc.get_mode()
    # get_mode returns a string ('sim' or 'real')
    click.echo(json.dumps({"mode": result}, indent=2, ensure_ascii=False))


@sim.command("connect")
@click.argument("number")
def connect(number):
    """Simulate connecting a phone number."""
    result = svc.sim_connect(number)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@sim.command("disconnect")
@click.argument("number")
def disconnect(number):
    """Simulate disconnecting a phone number."""
    result = svc.sim_disconnect(number)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@sim.command("send")
@click.argument("number")
@click.option("--text", required=True, help="Message text to send")
@click.option("--from-name", default="Contacto", show_default=True)
@click.option("--from-phone", default="0000000000", show_default=True)
def send(number, text, from_name, from_phone):
    """Simulate receiving an inbound message on a session."""
    result = asyncio.run(svc.sim_send(number=number, text=text, from_name=from_name, from_phone=from_phone))
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
