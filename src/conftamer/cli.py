from pathlib import Path

import typer

from conftamer.contexttrack import load_contexttrack
from conftamer.pmgraph.io import write_pmgraph_json

app = typer.Typer()


@app.callback()
def cli() -> None:
    pass


@app.command()
def build(
    input_path: Path,
    module_id: str = typer.Option(..., "--module-id"),
    output: Path = typer.Option(..., "--output"),
) -> None:
    try:
        write_pmgraph_json(load_contexttrack(input_path, module_id=module_id), output)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"Cannot build {input_path}: {error}", err=True)
        raise typer.Exit(code=2) from error


if __name__ == "__main__":
    app()
