import json
from pathlib import Path
from typing import Annotated

import typer

from conftamer.appgraph.models import Graph
from conftamer.contexttrack import load_contexttrack
from conftamer.igraph_ops import write_graphml
from conftamer.io import graph_to_json, load_graph_json
from conftamer.pmgraph.io import write_pmgraph_json
from conftamer.query import find_parameters, query_paths, query_subgraph

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
    """Build a message-only PMGraph from normalized ContextTrack v1 JSONL."""
    try:
        write_pmgraph_json(load_contexttrack(input_path, module_id=module_id), output)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"Cannot build {input_path}: {error}", err=True)
        raise typer.Exit(code=2) from error


def _check_query_options(node: str | None, key: str | None, module: str | None) -> None:
    if (node is None) == (key is None):
        raise ValueError("give exactly one of --node and --key")
    if module is not None and key is None:
        raise ValueError("--module only applies to --key")


def _parameter_id(graph: Graph, key: str, module: str | None) -> str:
    matches = find_parameters(graph, key, module)
    where = "" if module is None else f" in module {module!r}"
    if not matches:
        raise ValueError(f"no parameter has key {key!r}{where}")
    if len(matches) > 1:
        hint = (
            "use --node"
            if module is not None
            else "narrow it with --module or use --node"
        )
        raise ValueError(
            f"key {key!r}{where} matches {len(matches)} parameters: "
            f"{', '.join(matches)}; {hint}"
        )
    return matches[0]


@app.command()
def query(
    input_path: Path,
    node: Annotated[str | None, typer.Option("--node")] = None,
    key: Annotated[str | None, typer.Option("--key")] = None,
    module: Annotated[str | None, typer.Option("--module")] = None,
    paths: Annotated[bool, typer.Option("--paths")] = False,
) -> None:
    """Query a node in a PMGraph or AppGraph JSON file.

    Name the node with --node, or name a parameter by its configuration key with
    --key (narrowed to one module with --module if the key is in several).

    Prints the subgraph holding the node, everything that can influence it, and
    everything it can influence, as graph JSON that export accepts.

    With --paths, prints an object holding that subgraph and every root-to-leaf
    path through the node instead. That object is not a graph file, and listing
    paths can be very slow on large or densely connected graphs.
    """
    try:
        _check_query_options(node, key, module)
        graph = load_graph_json(input_path)
        node_id = node if key is None else _parameter_id(graph, key, module)
        assert node_id is not None
        payload = graph_to_json(query_subgraph(graph, node_id))
        if paths:
            payload = {"subgraph": payload, "paths": query_paths(graph, node_id)}
    except (OSError, ValueError) as error:
        typer.echo(f"Cannot query {input_path}: {error}", err=True)
        raise typer.Exit(code=2) from error
    # ASCII-safe, so the output can be saved and loaded again whatever encoding
    # stdout uses; the graph loader reads UTF-8 only.
    typer.echo(json.dumps(payload, indent=2))


@app.command("export")
def export_graph(
    input_path: Path,
    output: Annotated[Path, typer.Option(..., "--output")],
) -> None:
    """Export a PMGraph or AppGraph JSON file to GraphML."""
    try:
        write_graphml(load_graph_json(input_path), output)
    except (OSError, ValueError) as error:
        typer.echo(f"Cannot export {input_path} to {output}: {error}", err=True)
        raise typer.Exit(code=2) from error


if __name__ == "__main__":
    app()
