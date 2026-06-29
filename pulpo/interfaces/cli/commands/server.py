import click


@click.group()
def server():
    """Run Pulpo servers."""


@server.command("ui")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=8000, show_default=True)
def serve_ui(host, port):
    """Start the UI server (with auth)."""
    import uvicorn
    from pulpo.interfaces.ui.app import create_ui_app
    uvicorn.run(create_ui_app(), host=host, port=port)


@server.command("api")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8001, show_default=True)
def serve_api(host, port):
    """Start the raw API server (no auth)."""
    import uvicorn
    from pulpo.interfaces.api.app import create_api_app
    uvicorn.run(create_api_app(), host=host, port=port)
