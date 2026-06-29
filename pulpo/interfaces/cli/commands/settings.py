import json
import click
from pulpo.business import settings as svc


@click.group()
def settings():
    """Application settings."""


@settings.command("show")
def show_settings():
    """Show current settings."""
    result = svc.read_settings()
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@settings.command("set")
@click.argument("key")
@click.argument("value")
def set_setting(key, value):
    """Set a setting value. Example: set wa_poll_interval_seconds 300"""
    # Attempt to coerce numeric values
    coerced: int | str
    try:
        coerced = int(value)
    except ValueError:
        coerced = value

    # write_settings only knows about wa_poll_interval_seconds
    if key == "wa_poll_interval_seconds" and isinstance(coerced, int):
        try:
            result = svc.write_settings(wa_poll_interval_seconds=coerced)
            click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        except (ValueError, KeyError) as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(1)
    else:
        click.echo(f"Unknown setting key: {key}", err=True)
        raise SystemExit(1)
