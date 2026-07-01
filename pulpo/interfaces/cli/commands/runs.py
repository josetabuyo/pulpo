import asyncio
import json
import click
from pulpo.core import db


@click.group()
def runs():
    """Flow execution history (journal)."""


@runs.command("list")
@click.option("--bot-id", required=True, help="Bot ID")
@click.option("--limit", default=20, show_default=True, help="Max runs to show")
def list_runs(bot_id, limit):
    """List recent flow executions for a bot."""
    result = asyncio.run(db.get_flow_runs(bot_id, limit=limit))
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@runs.command("get")
@click.argument("run_id")
def get_run(run_id):
    """Show a flow execution with all its node steps."""
    async def _fetch():
        run = await db.get_flow_run(run_id)
        if not run:
            return None
        run["steps"] = await db.get_flow_run_steps(run_id)
        return run

    result = asyncio.run(_fetch())
    if not result:
        click.echo(f"Run '{run_id}' no encontrado.", err=True)
        raise SystemExit(1)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
