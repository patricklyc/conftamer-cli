import errno
import json
from pathlib import Path
from typing import Annotated

import typer

from conftamer.appgraph.stitch import stitch_with_dropped
from conftamer.contexttrack import load_contexttrack
from conftamer.io import (
    graph_to_json,
    load_graph_json,
    load_pmgraph_json,
    write_dropped_json,
    write_graph_json,
    write_graphml,
)
from conftamer.query import Graph, find_parameters
from conftamer.query import query as query_graph

app = typer.Typer()


def _fail(message: str, error: Exception) -> typer.Exit:
    typer.echo(f"{message}: {error}", err=True)
    return typer.Exit(code=2)


@app.callback()
def cli() -> None:
    pass


@app.command()
def build(
    input_path: Path,
    module_id: Annotated[str, typer.Option(..., "--module-id")],
    output: Annotated[Path, typer.Option(..., "--output")],
) -> None:
    """Build a PMGraph from a ContextTrack JSONL capture."""
    try:
        write_graph_json(load_contexttrack(input_path, module_id=module_id), output)
    except (OSError, TypeError, ValueError) as error:
        raise _fail(f"Cannot build {input_path}", error) from error


@app.command()
def stitch(
    input_paths: list[Path],
    output: Annotated[Path, typer.Option(..., "--output")],
    dropped: Annotated[Path | None, typer.Option("--dropped")] = None,
) -> None:
    """Stitch PMGraph JSON files into one AppGraph.

    With --dropped, also write every input message left out of the AppGraph,
    with the reason it was dropped.
    """
    try:
        result = stitch_with_dropped(load_pmgraph_json(path) for path in input_paths)
        # Check --dropped before writing anything, so a bad --dropped doesn't
        # leave the AppGraph written without its report.
        if dropped is not None:
            if dropped.resolve() == output.resolve():
                raise ValueError("--dropped and --output must be different files")
            if dropped.exists():
                raise FileExistsError(errno.EEXIST, "File exists", str(dropped))
        write_graph_json(result.appgraph, output)
        if dropped is not None:
            write_dropped_json(result.dropped, dropped)
    except (OSError, ValueError) as error:
        raise _fail("Cannot stitch", error) from error


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
) -> None:
    """Query a node in a PMGraph or AppGraph JSON file.

    Name the node with --node, or name a parameter by its configuration key with
    --key (narrowed to one module with --module if the key is in several).
    """
    try:
        _check_query_options(node, key, module)
        graph = load_graph_json(input_path)
        node_id = node if key is None else _parameter_id(graph, key, module)
        assert node_id is not None
        result = query_graph(graph, node_id)
    except (OSError, ValueError) as error:
        raise _fail(f"Cannot query {input_path}", error) from error
    payload = {"subgraph": graph_to_json(result.subgraph), "paths": result.paths}
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("export")
def export_graph(
    input_path: Path,
    output: Annotated[Path, typer.Option(..., "--output")],
) -> None:
    """Export a PMGraph or AppGraph JSON file to GraphML."""
    try:
        write_graphml(load_graph_json(input_path), output)
    except (OSError, ValueError) as error:
        raise _fail(f"Cannot export {input_path} to {output}", error) from error


if __name__ == "__main__":
    app()
