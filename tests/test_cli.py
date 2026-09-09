from typer.testing import CliRunner

from conftamer.cli import app

runner = CliRunner()


def test_app():
    result = runner.invoke(app, ["World"])
    assert result.exit_code == 0
    assert "Hello World!" in result.output
