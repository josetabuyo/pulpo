import click
from .commands import bots, flows, connections, contacts, messages, settings, server, runs


@click.group()
def cli():
    """Pulpo — bot orchestration CLI."""


cli.add_command(bots.bots)
cli.add_command(flows.flows)
cli.add_command(connections.connections)
cli.add_command(contacts.contacts)
cli.add_command(messages.messages)
cli.add_command(settings.settings)
cli.add_command(server.server)
cli.add_command(runs.runs)
