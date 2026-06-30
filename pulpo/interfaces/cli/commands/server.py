import click


@click.group()
def server():
    """Run Pulpo servers."""


@server.command("ui")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=8000, show_default=True)
@click.option("--reload", is_flag=True, default=False, help="Auto-reload on code changes (dev only).")
def serve_ui(host, port, reload):
    """Start the UI server (with auth)."""
    import uvicorn
    if reload:
        uvicorn.run(
            "pulpo.interfaces.ui.app:create_ui_app",
            host=host, port=port, reload=True, factory=True,
        )
    else:
        from pulpo.interfaces.ui.app import create_ui_app
        uvicorn.run(create_ui_app(), host=host, port=port, log_level="info")


@server.command("api")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8001, show_default=True)
def serve_api(host, port):
    """Start the raw API server (no auth)."""
    import uvicorn
    from pulpo.interfaces.api.app import create_api_app
    uvicorn.run(create_api_app(), host=host, port=port)
