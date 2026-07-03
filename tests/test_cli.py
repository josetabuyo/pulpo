"""
Tests del CLI de pulpo — comandos disponibles y flags correctos.
No requiere servidor corriendo.
"""
from click.testing import CliRunner
from pulpo.interfaces.cli.main import cli


def test_cli_top_level_groups():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for group in ["bots", "flows", "connections", "contacts", "settings", "server"]:
        assert group in result.output


def test_server_ui_has_reload_flag():
    runner = CliRunner()
    result = runner.invoke(cli, ["server", "ui", "--help"])
    assert result.exit_code == 0
    assert "--reload" in result.output
    assert "--port" in result.output
    assert "--host" in result.output


def test_server_api_flags():
    runner = CliRunner()
    result = runner.invoke(cli, ["server", "api", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.output
    assert "--host" in result.output


def test_bots_list_command_exists():
    runner = CliRunner()
    result = runner.invoke(cli, ["bots", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output


def test_flows_node_types_command_exists():
    runner = CliRunner()
    result = runner.invoke(cli, ["flows", "--help"])
    assert result.exit_code == 0
    assert "node-types" in result.output


def test_flows_duplicate_command_exists_and_documented():
    runner = CliRunner()
    result = runner.invoke(cli, ["flows", "--help"])
    assert result.exit_code == 0
    assert "duplicate" in result.output

    detail = runner.invoke(cli, ["flows", "duplicate", "--help"])
    assert detail.exit_code == 0
    assert "--bot-id" in detail.output
    assert "--flow-id" in detail.output
    assert "--name" in detail.output
    # El help debe explicar el comportamiento clave: copia campos y queda inactivo.
    assert "INACTIVO" in detail.output
    assert "Guardar como" in detail.output


def test_flows_update_help_documents_active_toggle():
    runner = CliRunner()
    result = runner.invoke(cli, ["flows", "update", "--help"])
    assert result.exit_code == 0
    assert "active" in result.output
