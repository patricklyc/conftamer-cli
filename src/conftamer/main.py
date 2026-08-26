import sys
from enum import Enum
from pathlib import Path
from typing import Annotated, Never

import igraph as ig
import typer
from rich import print

from conftamer.contexttrack import parse_contexttrack
from conftamer.csv_graph import find_nodes, read_csv, to_graph, to_subgraph
from conftamer.pmgraph import write_pmgraph

app = typer.Typer()


@app.command()
def contexttrack(
    input_path: Path,
    module_id: Annotated[str, typer.Option()],
    output: Annotated[Path | None, typer.Option()] = None,
):
    result = parse_contexttrack(input_path, module_id=module_id)
    output_path = output or Path(f"{input_path}.pmgraph.json")
    write_pmgraph(result.graph, output_path)

    for warning in result.warnings:
        print(
            f"warning: line {warning.input_line}: {warning.message}",
            file=sys.stderr,
        )


@app.command()
def graph(filename: str):
    edges = read_csv(filename)

    g = to_graph(edges)
    print(g)
    g.write_graphml(f"{filename}.graphml")


def _exit_with_error(message: str) -> Never:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


def _format_node(graph: ig.Graph, node_id: int) -> str:
    attributes = []
    for name, value in sorted(graph.vs[node_id].attributes().items()):
        if value is None:
            continue
        if isinstance(value, Enum):
            value = value.value
        attributes.append(f"{name}={value!r}")
    return f"node {node_id}: {', '.join(attributes)}"


def _select_node(graph: ig.Graph, query: str) -> int:
    try:
        node_id = int(query.strip())
    except ValueError:
        pass
    else:
        if not 0 <= node_id < graph.vcount():
            _exit_with_error(
                f"node id {node_id} is out of range for graph with "
                f"{graph.vcount()} nodes"
            )
        return node_id

    try:
        matches = find_nodes(graph, query)
    except ValueError as error:
        _exit_with_error(str(error))

    if not matches:
        _exit_with_error(f"no nodes match {query!r}")
    if len(matches) == 1:
        return matches[0]

    typer.echo(f"Multiple nodes match {query!r}:")
    for choice, node_id in enumerate(matches, start=1):
        print(f"{choice}. {_format_node(graph, node_id)}")

    try:
        selection = typer.prompt(
            f"Select a node [1-{len(matches)}]",
            type=int,
        )
    except typer.Abort:
        _exit_with_error("a selection is required when multiple nodes match")

    if not 1 <= selection <= len(matches):
        _exit_with_error(f"selection must be between 1 and {len(matches)}")
    return matches[selection - 1]


@app.command()
def subgraph(filename: str, query: str):
    graph = to_graph(read_csv(filename))
    node_id = _select_node(graph, query)
    to_subgraph(graph, node_id).write_graphml(f"{filename}.graphml")


if __name__ == "__main__":
    app()
