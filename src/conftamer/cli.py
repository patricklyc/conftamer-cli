import json
from pathlib import Path
from typing import Annotated

import typer

from conftamer.contexttrack import load_contexttrack
from conftamer.pmgraph.igraph_ops import query_node, write_graphml
from conftamer.pmgraph.io import load_pmgraph_json, write_pmgraph_json

app = typer.Typer()


@app.callback()
def cli() -> None:
    pass


@app.command()
def build(
    input_path: Path,
    module_id: Annotated[str, typer.Option(..., "--module-id")],
    output: Annotated[Path, typer.Option(..., "--output")],
) -> None:
    try:
        write_pmgraph_json(load_contexttrack(input_path, module_id=module_id), output)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"Cannot build {input_path}: {error}", err=True)
        raise typer.Exit(code=2) from error


@app.command()
def query(
    input_path: Path,
    node: Annotated[str, typer.Option(..., "--node")],
) -> None:
    try:
        result = query_node(load_pmgraph_json(input_path), node)
    except (OSError, ValueError) as error:
        typer.echo(f"Cannot query {input_path}: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(json.dumps(result, indent=2))


@app.command("export")
def export_graph(
    input_path: Path,
    output: Annotated[Path, typer.Option(..., "--output")],
) -> None:
    try:
        write_graphml(load_pmgraph_json(input_path), output)
    except (OSError, ValueError) as error:
        typer.echo(f"Cannot export {input_path} to {output}: {error}", err=True)
        raise typer.Exit(code=2) from error


if __name__ == "__main__":
    app()
